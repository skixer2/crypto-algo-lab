#!/usr/bin/env python3
"""PILOT A runner — GBM rule-extractor falsification pilot (pre-registered).

Spec: reports/nn_search_paths_20261028/PILOT_A_SPEC.md (frozen BEFORE this run).
Read-only wrt the repo; writes only under reports/nn_search_paths_20261028/ except
temporary screening copies in models/alpha_formulas/ (md5-recorded, removed after).

Stages:
  --stage diag     AUC table + K1 verdict (kills or passes the extractor)
  --stage extract  --horizon {96,672}: rule extraction -> candidates/*.py
  --stage control  grammar-enumeration control arm -> candidates/nnC_*.py
  --stage screen   validate + screen_candidate every candidates/*.py (verbatim capture)
"""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
OUT = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(OUT, "candidates")
DIAG = os.path.join(OUT, "diag_results.json")

ETH_CSV = os.path.join(ROOT, "framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv")
BTC_CSV = os.path.join(ROOT, "framework/data_cache/okx_BTC_USDT_15m_20210101_20260928.csv")
FEE = 0.0008
SEED = 7
SCREEN_FEATS = ["f_ret24", "f_ret7d", "f_vol24", "f_atr", "f_chan", "f_disth",
                "f_fund", "f_volratio", "f_tod_sin", "f_tod_cos"]
DIAG_FEATS = ["f_btc30", "f_rs30"]
ALL_FEATS = SCREEN_FEATS + DIAG_FEATS
FOLDS = [("F1", "2021-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
         ("F2", "2021-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
         ("F3", "2021-01-01", "2024-12-31", "2025-01-01", "2026-06-30")]


def load_frame():
    from tuner.alpha_orchestrator import build_fund_pct
    c = pd.read_csv(ETH_CSV)
    c.columns = [x.lower() for x in c.columns]
    c["timestamp"] = pd.to_datetime(c["timestamp"], utc=True)
    c = c.set_index("timestamp")
    c = c[~c.index.duplicated(keep="first")]
    c["fund_pct"] = build_fund_pct(
        c.reset_index()[["timestamp", "open", "high", "low", "close"]].set_index("timestamp"),
        "binance", "ETH/USDT")
    lr = np.log(c["close"] / c["close"].shift(1))
    f = pd.DataFrame(index=c.index)
    f["f_ret24"] = np.log(c["close"] / c["close"].shift(96))
    f["f_ret7d"] = np.log(c["close"] / c["close"].shift(672))
    f["f_vol24"] = lr.rolling(96).std()
    tr = pd.concat([c["high"] - c["low"], (c["high"] - c["close"].shift(1)).abs(),
                    (c["low"] - c["close"].shift(1)).abs()], axis=1).max(axis=1)
    f["f_atr"] = tr.rolling(96, min_periods=32).mean() / c["close"]
    ch_hi = c["high"].rolling(192, min_periods=96).max().shift(1)
    ch_lo = c["low"].rolling(192, min_periods=96).min().shift(1)
    f["f_chan"] = (c["close"] - ch_lo) / (ch_hi - ch_lo)
    f["f_disth"] = c["close"] / ch_hi - 1.0
    f["f_fund"] = c["fund_pct"]
    f["f_volratio"] = f["f_vol24"] / lr.rolling(2016).std()
    bod = c.index.hour * 4 + c.index.minute // 15
    phase = 2.0 * np.pi * bod / 96.0
    f["f_tod_sin"] = np.sin(phase)
    f["f_tod_cos"] = np.cos(phase)
    b = pd.read_csv(BTC_CSV)
    b.columns = [x.lower() for x in b.columns]
    b["timestamp"] = pd.to_datetime(b["timestamp"], utc=True)
    b = b.set_index("timestamp")[~b.index.duplicated(keep="first")]
    btc30 = np.log(b["close"] / b["close"].shift(2880)).reindex(c.index).ffill()
    eth30 = np.log(c["close"] / c["close"].shift(2880))
    f["f_btc30"] = btc30
    f["f_rs30"] = eth30 - btc30
    return c, f


def labels(c, H):
    fwd = c["close"].shift(-H) / c["open"].shift(-1) - 1.0
    return (fwd > 0.002).astype(float)


def fold_masks(index, f_tr0, f_tr1, v0, v1, H):
    tr = (index >= f_tr0) & (index <= f_tr1)
    embargo = index < (pd.Timestamp(v0, tz="UTC") - pd.Timedelta(minutes=15 * H))
    tr = tr & embargo
    va = (index >= v0) & (index <= v1)
    return tr, va


def stage_diag():
    c, f = load_frame()
    res = {"folds": [], "verdict": {}}
    models = {}
    for H in (96, 672):
        y = labels(c, H)
        df = f.copy()
        df["y"] = y
        df = df.dropna()
        idx = df.index
        for name, t0, t1, v0, v1 in FOLDS:
            tr, va = fold_masks(idx, t0, t1, v0, v1, H)
            Xtr, ytr = df.loc[tr, ALL_FEATS], df.loc[tr, "y"]
            Xva, yva = df.loc[va, ALL_FEATS], df.loc[va, "y"]
            r, m2 = fit_models(Xtr, ytr, Xva, yva)
            models[(H, name)] = m2
            res["folds"].append(dict(H=H, fold=name, **r))
            print(f"H{H} {name}: M1 {r['M1']['train_auc']:.3f}->{r['M1']['valid_auc']}  "
                  f"M2 {r['M2']['train_auc']:.3f}->{r['M2']['valid_auc']}  "
                  f"base {r['base_rate_valid']:.3f}  n={r['n_train']}/{r['n_valid']}")
    for H in (96, 672):
        v = [x["M2"]["valid_auc"] for x in res["folds"] if x["H"] == H and x["M2"]["valid_auc"]]
        g = [x["M2"]["train_auc"] - x["M2"]["valid_auc"] for x in res["folds"]
             if x["H"] == H and x["M2"]["valid_auc"]]
        med = float(np.median(v)) if v else 0.5
        gap2 = sum(1 for x in g if x > 0.15)
        res["verdict"][f"H{H}"] = dict(median_valid_auc_m2=med, folds_gap_gt_015=gap2,
                                       k1_transfer=med >= 0.53, k1_gap_ok=gap2 < 2)
    alive = [h for h in ("H96", "H672")
             if res["verdict"][h]["k1_transfer"] and res["verdict"][h]["k1_gap_ok"]]
    res["verdict"]["K1"] = "ALIVE" if alive else "DEAD"
    res["verdict"]["alive_horizons"] = alive
    with open(DIAG, "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print("K1 VERDICT:", res["verdict"]["K1"], alive)


def fit_models(Xtr, ytr, Xva, yva):
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import HistGradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    out = {}
    mu, sd = Xtr.mean(), Xtr.std().replace(0, 1.0)
    m1 = LogisticRegression(penalty="l1", solver="liblinear", C=0.1, max_iter=1000)
    Xtr_s, Xva_s = (Xtr - mu) / sd, (Xva - mu) / sd
    m1.fit(Xtr_s, ytr)
    out["M1"] = dict(train_auc=float(roc_auc_score(ytr, m1.predict_proba(Xtr_s)[:, 1])),
                     valid_auc=float(roc_auc_score(yva, m1.predict_proba(Xva_s)[:, 1]))
                     if len(np.unique(yva)) > 1 else None)
    m2 = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                        min_samples_leaf=500, l2_regularization=1.0,
                                        random_state=SEED)
    m2.fit(Xtr, ytr)
    out["M2"] = dict(train_auc=float(roc_auc_score(ytr, m2.predict_proba(Xtr)[:, 1])),
                     valid_auc=float(roc_auc_score(yva, m2.predict_proba(Xva)[:, 1]))
                     if len(np.unique(yva)) > 1 else None)
    out["base_rate_valid"] = float(np.mean(yva))
    out["n_train"], out["n_valid"] = int(len(ytr)), int(len(yva))
    return out, m2


# ---------------- extraction ----------------

def leaf_paths(m2):
    """Yield (constraint list [(feat, thr, side)], leaf_prob, count) from a fitted HistGB."""
    cols = list(m2.feature_names_in_)
    paths = []
    for pred_iter in m2._predictors:
        for tp in pred_iter:
            nodes = tp.nodes

            def walk(i, cons):
                nd = nodes[i]
                if nd["is_leaf"]:
                    p = 1.0 / (1.0 + np.exp(-nd["value"]))
                    paths.append((list(cons), float(p), int(nd["count"])))
                    return
                feat = cols[nd["feature_idx"]]
                thr = float(nd["num_threshold"])
                walk(nd["left"], cons + [(feat, thr, "le")])
                walk(nd["right"], cons + [(feat, thr, "gt")])

            walk(0, [])
    return paths


def stage_extract(horizon):
    c, f = load_frame()
    H = horizon
    y = labels(c, H)
    df = f.copy()
    df["y"] = y
    df = df.dropna()
    idx = df.index
    per_fold = {}
    for name, t0, t1, v0, v1 in FOLDS:
        tr, va = fold_masks(idx, t0, t1, v0, v1, H)
        Xtr, ytr = df.loc[tr, ALL_FEATS], df.loc[tr, "y"]
        m2 = HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
                                            min_samples_leaf=500, l2_regularization=1.0,
                                            random_state=SEED)
        m2.fit(Xtr, ytr)
        sup = max(2000, int(0.01 * len(ytr)))
        kept = [(cons, p, n) for cons, p, n in leaf_paths(m2)
                if p >= 0.55 and n >= sup and all(ft in SCREEN_FEATS for ft, _, _ in cons)]
        dropped_diag = sum(1 for cons, p, n in leaf_paths(m2)
                           if p >= 0.55 and n >= sup and any(ft in DIAG_FEATS for ft, _, _ in cons))
        per_fold[name] = dict(rules=kept, dropped_diagnostic=dropped_diag,
                              Xva=df.loc[va, SCREEN_FEATS], total_kept_all=kept and None)
        print(f"{name}: leaves kept {len(kept)} (dropped-diag {dropped_diag})")
    # dedupe by signature
    def sig(cons):
        return tuple(sorted((ft, sd_, float(f"{th:.4g}")) for ft, th, sd_ in cons))
    seen, uniq = {}, []
    for name in per_fold:
        for cons, p, n in per_fold[name]["rules"]:
            s = sig(cons)
            if s not in seen:
                seen[s] = name
                uniq.append((s, cons, name))
    # stability: same feature+side set, thresholds within 15% relative, in >=2 folds
    stable = []
    for s, cons, home in uniq:
        feats = sorted(set((ft, sd_) for ft, _, sd_ in cons))
        fams = []
        for s2, cons2, home2 in uniq:
            if home2 == home or sorted(set((ft, sd_) for ft, _, sd_ in cons2)) != feats:
                continue
            if len(cons2) != len(cons):
                continue
            ok = True
            m1 = {(ft, sd_): th for ft, th, sd_ in cons}
            m2_ = {(ft, sd_): th for ft, th, sd_ in cons2}
            for k in m1:
                a, b = m1[k], m2_[k]
                if abs(a - b) > 0.15 * max(abs(a), abs(b), 1e-9):
                    ok = False
                    break
            if ok:
                fams.append((s2, cons2, home2))
        if fams:
            stable.append((cons, home, fams))
    print(f"unique {len(uniq)}, stable-in->=-2-folds {len(stable)}")
    # valid precision on home fold (and family folds), best kept
    scored = []
    for cons, home, fams in stable:
        best = 0.0
        for cand in [(cons, home)] + fams:
            _, ch, hn = cand
            Xva = per_fold[hn]["Xva"]
            mask = np.ones(len(Xva), bool)
            for ft, th, sd_ in ch:
                mask &= (Xva[ft].values <= th) if sd_ == "le" else (Xva[ft].values > th)
            if mask.sum() >= 200:
                best = max(best, float(mask.mean()))
        scored.append((best, cons, home))
    scored.sort(reverse=True)
    os.makedirs(CAND, exist_ok=True)
    n_written = 0
    for i, (prec, cons, home) in enumerate(scored[:10]):
        n_written += 1
        write_formula(os.path.join(CAND, f"nn1_{i+1:03d}.py"), cons,
                      extra=f"# extracted from fold {home}, valid-region share {prec:.3f}")
    print(f"wrote {n_written} candidate formulas -> {CAND}")
    total_dropped = sum(per_fold[n]["dropped_diagnostic"] for n in per_fold)
    total_kept = sum(len(per_fold[n]["rules"]) for n in per_fold)
    with open(os.path.join(OUT, "extract_stats.json"), "w") as fh:
        json.dump(dict(horizon=H, leaves_kept=total_kept, dropped_diagnostic=total_dropped,
                       diag_share=(total_dropped / max(1, total_dropped + total_kept)),
                       unique=len(uniq), stable=len(stable), written=n_written),
                  fh, indent=1)


def write_formula(path, cons, extra=""):
    conds = []
    for ft, th, sd_ in cons:
        op = "<=" if sd_ == "le" else ">"
        conds.append(f"    rule &= (X[\"{ft}\"] {op} {th:.6g})")
    body = "\n".join(conds)
    txt = f'''# LINEAGE: NNPILOT-A-20261028 (GBM rule-extractor, H={ {96:'1d',672:'7d'} }, fold-stable leaf path)
# Machine-generated candidate. Pre-registered pilot: PILOT_A_SPEC.md. NOT a proposal card;
# screens once canonically; cannot be seal-grade on extractor-seen data. {extra}
import numpy as np
import pandas as pd


def _features(df):
    close, high, low = df["close"], df["high"], df["low"]
    lr = np.log(close / close.shift(1))
    X = pd.DataFrame(index=df.index)
    X["f_ret24"] = np.log(close / close.shift(96))
    X["f_ret7d"] = np.log(close / close.shift(672))
    X["f_vol24"] = lr.rolling(96).std()
    tr = pd.concat([high - low, (high - close.shift(1)).abs(),
                    (low - close.shift(1)).abs()], axis=1).max(axis=1)
    X["f_atr"] = tr.rolling(96, min_periods=32).mean() / close
    ch_hi = high.rolling(192, min_periods=96).max().shift(1)
    ch_lo = low.rolling(192, min_periods=96).min().shift(1)
    X["f_chan"] = (close - ch_lo) / (ch_hi - ch_lo)
    X["f_disth"] = close / ch_hi - 1.0
    fund = df["fund_pct"] if "fund_pct" in df.columns else pd.Series(np.nan, index=df.index)
    X["f_fund"] = fund
    X["f_volratio"] = X["f_vol24"] / lr.rolling(2016).std()
    bod = df.index.hour * 4 + df.index.minute // 15
    ph = 2.0 * np.pi * bod / 96.0
    X["f_tod_sin"] = np.sin(ph)
    X["f_tod_cos"] = np.cos(ph)
    return X


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    X = _features(df)
    rule = pd.Series(True, index=df.index)
{body}
    pos = rule.astype(float)
    return pos.fillna(0.0).clip(0.0, 1.0)
'''
    with open(path, "w") as fh:
        fh.write(txt)


# ---------------- control arm ----------------

def stage_control():
    c, f = load_frame()
    df = f[SCREEN_FEATS].dropna()
    tr = df.loc["2021-01-01":"2023-12-31"]
    qs = {ft: np.quantile(tr[ft].values, [0.2, 0.4, 0.6, 0.8]) for ft in SCREEN_FEATS}
    sel = df.loc["2024-01-01":"2026-06-30"]
    ret = c["close"].pct_change().reindex(sel.index).fillna(0.0).values
    months = sel.index.to_period("M").astype(str).values
    codes, uniq_m = pd.factorize(months)
    nM = len(uniq_m)
    bench_m = np.bincount(codes, weights=ret, minlength=nM)
    sl = slice(None)
    masks = {}
    for ft in SCREEN_FEATS:
        v = sel[ft].values
        for q in qs[ft]:
            masks[(ft, float(q), "le")] = v <= q
            masks[(ft, float(q), "gt")] = v > q
    scored = []
    keys = list(masks.keys())
    for i, (f1, t1, s1) in enumerate(keys):
        cands = [( (f1, t1, s1), )]
        for (f2, t2, s2) in keys[i + 1:]:
            if f2 == f1:
                continue
            cands.append(((f1, t1, s1), (f2, t2, s2)))
        for rule in cands:
            m = masks[rule[0]].copy()
            for r in rule[1:]:
                m &= masks[r]
            sup = int(m.sum())
            if sup < 500:
                continue
            pos = m.astype(float)
            dpos = np.abs(np.diff(pos, prepend=0.0))
            pos_l = np.concatenate([[0.0], pos[:-1]])
            book = pos_l * ret - FEE * dpos
            book_m = np.bincount(codes, weights=book, minlength=nM)
            exc = float((book_m - bench_m).mean() * 100)
            scored.append((exc, rule, sup))
    scored.sort(reverse=True)
    os.makedirs(CAND, exist_ok=True)
    for i, (exc, rule, sup) in enumerate(scored[:5]):
        cons = [(ft, th, sd_) for ft, th, sd_ in rule]
        write_formula(os.path.join(CAND, f"nnC_{i+1:03d}.py"), cons,
                      extra=f"[CONTROL] selection excess {exc:.3f}%/mo, support {sup} bars (selection-only number)")
    print(f"control: {len(scored)} scorable rules, wrote top-5")
    with open(os.path.join(OUT, "control_stats.json"), "w") as fh:
        json.dump(dict(scorable=len(scored),
                       top=[dict(exc=round(e, 4), rule=[list(r) for r in ru], sup=s)
                            for e, ru, s in scored[:5]]), fh, indent=1, default=str)


# ---------------- screening ----------------

def stage_screen():
    files = sorted(os.listdir(CAND)) if os.path.isdir(CAND) else []
    results = []
    for fn in files:
        if not fn.endswith(".py"):
            continue
        src = os.path.join(CAND, fn)
        md5 = hashlib.md5(open(src, "rb").read()).hexdigest()
        name = fn[:-3]
        dst = os.path.join(ROOT, "models/alpha_formulas", fn)
        shutil.copy(src, dst)
        env = dict(os.environ, MPLCONFIGDIR="/tmp/ml")
        r = subprocess.run([sys.executable, os.path.join(ROOT, "tuner/validate_formula.py"), dst],
                           capture_output=True, text=True, env=env)
        val = r.stdout.strip().splitlines()
        verdict_line = next((l for l in val if '"verdict"' in l), "validate: ?")
        r2 = subprocess.run([sys.executable, os.path.join(ROOT, "tools/screen_candidate.py"), dst],
                            capture_output=True, text=True, env=env, cwd=ROOT)
        os.remove(dst)
        results.append(dict(name=name, md5=md5, validate=verdict_line.strip(),
                            screen=r2.stdout.strip(), err=r2.stderr[-500:]))
        print(f"=== {name} (md5 {md5[:8]}) {verdict_line.strip()}")
        print(r2.stdout.strip() or r2.stderr[-300:])
    with open(os.path.join(OUT, "screen_results.json"), "w") as fh:
        json.dump(results, fh, indent=1)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True, choices=["diag", "extract", "control", "screen"])
    ap.add_argument("--horizon", type=int, default=96, choices=[96, 672])
    a = ap.parse_args()
    if a.stage == "diag":
        stage_diag()
    elif a.stage == "extract":
        stage_extract(a.horizon)
    elif a.stage == "control":
        stage_control()
    else:
        stage_screen()
