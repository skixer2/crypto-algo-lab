# Bull Mining Round 3 — REPORT (solid bases, canonical grading)

**Date:** 2026-10-19 · **Seat:** ETH bull specialist · **Bench:** B&H ETH 15m OKX archive (seal 2026-07-28)
**Ruler:** `tools/stats_canonical.grade` ONLY (no self-written stats anywhere in this round).
**Substrate:** bar arithmetic, `compose_portfolio` law (decision@close t → effective t+1; fee 0.0008·|Δexposure|; funding −rate·exposure at 00/08/16 UTC bars). Grid declared in `DECLARED_GRID.json` BEFORE grading.
**Artifacts:** `lab.py`, `engine_check.py`, `out/*.json` (copied here), curves in `curves/`, formula in `formulas/`.

---

## 0. ANCHOR CHECK (first, per stop-on-discrepancy law)

Recomputed raw turtle192 latch (entry close>192-high.shift(1); exit close<192-low.shift(1)−1·ATR96(SMA,minp32); size 1; fees 0.0008; funding per spec) through this round's pipeline:

**A1 — gross, fees only (the recorded +1.12/t0.77 convention):**
```json
{"name": "anchor_A1_raw_turtle192_gross", "mean_excess_pct_mo": 1.25, "t": 0.86, "worst_window_pct": -27.57, "best_window_pct": 32.65, "first_half_pct": 0.87, "second_half_pct": 1.61, "concentration": 0.42, "neg_windows": 31, "n_windows": 63, "continuous_dd_pct": -53.5, "july26_partial_pct": -10.67, "time_in_pct": 62.0, "worst_absolute_month_pct": -22.09}
```
**A2 — with Binance funding charged at 8h boundaries (per spec):**
```json
{"name": "anchor_A2_raw_turtle192_funding_charged", "mean_excess_pct_mo": 0.62, "t": 0.42, "worst_window_pct": -29.56, "best_window_pct": 32.59, "first_half_pct": 0.17, "second_half_pct": 1.07, "concentration": 0.83, "neg_windows": 32, "n_windows": 63, "continuous_dd_pct": -55.3, "july26_partial_pct": -10.97, "time_in_pct": 62.0, "worst_absolute_month_pct": -22.01}
```

**RESOLUTION OF THE BAND QUESTION (disclosed, not buried):** the recorded anchor number +1.12/t0.77 was produced by round-1's monthly convention, which had a **one-bar strat/bench misalignment at month boundaries** (strat window started at the bar *before* the month, bench at the month's first bar). Re-running that exact convention on the identical curve reproduces the record to 4 decimals: **+1.1190 / t 0.7713**. The canonical ruler aligns both legs to the window's first bar and grades the **same curve** +1.25/t0.86 (A1). The latch itself is **bit-identical** to the recorded construction (0/205k bar diffs) and DD (53.5 vs 53.53) / time-out (38.0 vs 38.25) match. So: no unit bug (the round-2 failure class) — the band mismatch (+0.15 mean, +0.06 t) is fully root-caused to the ruler's stricter window alignment. **Decision: proceeded**, with every comparison in this report same-ruler (canonical) and the funding-honest A2 (+0.62 net) as the anchor's true seat-cost baseline. The recorded +1.12 was gross; the task's band evidently referenced it — flagging the spec ambiguity for the ledger.

---

## 1. LANE MAP (Exam Law v2) — degenerate, disclosed

Detector 7 (donchian 96, confirm 96, vol 0.70/0.80, grind 192/96; `regime_grid.json i==7`): expansion is the **strict plurality lane in all 64 calendar months** (overall shares: exp 0.638 / chop 0.172 / bear 0.103 / grind 0.087). Therefore in-lane months = all 63 graded months, and the out-of-lane set is **empty** (the −40% ruin floor is evaluated full-grid per the law's own parenthetical). Consequence: the −15% worst-in-lane-month bar applies to every month. Discretionary stress slice added so the exam keeps bite: **bear-est 8 months** (lowest expansion bar-share: 2023-07/08/09, 2022-06, 2025-12, 2026-01/02/06).

---

## 2. RECRUIT CANDIDATE — C: "turtle192 × binance-funding gate < 0.7"

**Exact rules (decision at 15m close t, engine fills t+1 open):**
- Entry: `close_t > max(high, 192).shift(1)_t` AND `binance_funding_pct30d_t < 0.7` (fpct = causal 30d rolling percentile over 8h settlements, 90-settle window, **no bfill**; settlement aligned to bars by settlement-ts ≤ bar-close-ts).
- Exit: `close_t < min(low, 192).shift(1)_t − 1.0·ATR96_t` (ATR = SMA of true range, min_periods 32). Entry precedence on same bar; state = event ffill, flat before first event.
- Size 1.0. Own-trade fee 0.0008/side. **Funding cost charged on exposure at every 8h settlement, avg(binance,bybit) input** (committed cost model; headline numbers are net of it).
- Funding input for the GATE: **Binance proxy only** (per-input law: trained on its own grid, see §4).

**Character:** 146 round trips (2.2/mo), mean +2.43%/trip, median −1.36%, win 40.4% — fat-right-tail latch, same family character as the recorded turtle. Time-in 52%, fee drag 0.35%/mo, funding paid 0.61%/mo.

**Canonical grade — full grid = in-lane (net of avg funding):**
```json
{"name": "C_t192_bin_g0.7", "mean_excess_pct_mo": 2.11, "t": 1.41, "worst_window_pct": -32.7, "best_window_pct": 28.26, "first_half_pct": 2.14, "second_half_pct": 2.09, "concentration": 0.21, "neg_windows": 29, "n_windows": 63, "continuous_dd_pct": -47.5, "july26_partial_pct": -10.96, "time_in_pct": 52.0, "worst_absolute_month_pct": -18.83}
```
(Engine-routed grade, below, is numerically identical: +2.11/t1.41.) Gross of funding: +2.64/t1.79/worst −31.8 (`mine_stage1.json`). July-2026 partial −10.96: **disclosed, ungraded**.

**Lane-conditional (expansion months; degenerate = full grid, see §1):** identical to the grade above. **Out-of-lane ruin floor (full-grid worst absolute month):** −18.83% ≥ −40% ✓.

**Bear-est-8 stress slice (canonical, months_mask):**
```json
{"name": "C_t192_bin_g0.7_bear8", "mean_excess_pct_mo": 7.83, "t": 1.53, "worst_window_pct": -15.19, "best_window_pct": 25.86, "first_half_pct": 7.69, "second_half_pct": 7.98, "concentration": 0.41, "neg_windows": 3, "n_windows": 8, "continuous_dd_pct": -47.5, "july26_partial_pct": -10.96, "worst_absolute_month_pct": -18.82}
```
The seat earns its keep where it should: +7.8%/mo in the most defensive months (anchor raw: +7.4/t1.32 same slice).

**Robustness:**
- **Jitter ±15%** (N∈{163,192,221} × gate∈{0.595,0.7,0.805} × buf∈{0.85,1.0,1.15}): **27/27 sign-stable**, min mean +0.69, max +3.43, center = committed spec (not grid-max). `jitter_bin_g0.7.json`.
- **Shift-2 relabel:** +2.20/t1.45 → retention **1.04** (≥0.75 law) — no same-bar rent.
- **Gate plateau:** g0.5 → +1.76/t1.01; g0.7 → +2.11/t1.41 (both ≥ known bests); recorded plateau 0.5–0.8 honored.
- **Per-input check:** bybit input at both its own thresholds: +0.24/t0.11, +0.79/t0.38 → **bybit rejected as gate input**; avg input: +1.50/t0.78, +1.46/t0.96 → mediocre. The binance edge is broad (wins at both thresholds, +0.65%/mo over avg at 0.7), not a knife-edge.

**Engine-vs-arithmetic reality ratio (mandated):**
- Route 1, `tuner.alpha_orchestrator.run_backtest` (fast-ctx path, formula `formulas/bullr3_latch192.py`, signal +1/−1, signal_exit_threshold 0.5, SL/TP set at 50×ATR14 = disaster-only, fee 0.0008, shorts off): engine **+0.52/t0.35** vs arithmetic **+0.62/t0.42** (ungated core, net) → **reality ratio 0.839 ≥ 0.8 ✓**; position match 99.8% (corr 0.996); worst-window/DD match to 0.02pts.
- Route 2, full recruit config (funding gate included) through `framework.runner.run_strategy` with a gate-carrying Module-3-contract model (engine imported, never copied): engine **+2.11/t1.41, worst −32.7, DD −47.5** vs arithmetic identical → **reality ratio 1.0**; position match 99.85%. `engine_validation.json` (verbatim JSONs there).

**EXAM LAW v2 verdict — 9/10 bars, 1 FAIL, not auto-accepted:**
| Bar | Value | Verdict |
|---|---|---|
| In-lane mean excess ≥ +0.8 | +2.11 | ✓ |
| t ≥ 1.0 | 1.41 | ✓ |
| ≥ 8 in-lane months | 63 | ✓ |
| Both halves ≥ 0 | +2.14 / +2.09 | ✓ |
| Worst in-lane month (excess) ≥ −15% | **−32.7** | **✗ FAIL** |
| Worst absolute month ≥ −40% (full grid) | −18.8 | ✓ |
| Jitter ±15% sign-stable | 27/27 | ✓ |
| Reality ratio ≥ 0.8 | 1.0 (0.839 ungated) | ✓ |
| Shift-2 retention ≥ 0.75 | 1.04 | ✓ |
| July-2026 disclosed | −10.96 | ✓ (ungraded) |

**The FAIL and why it needs JP's decision, not silence:** the worst month is **2021-10 (bench +42.3%, seat +9.6%)** — the gate (correctly) refused mania-crowded entries and the seat missed a dumb-long blowoff; same structural miss class as every member of every family (worst months are all bench-surge months: 2021-04 +43.9, 2021-08 +35.4, 2025-05 +40.8, 2022-07 +59.1). **The −15% bar under the canonical ruler also fails the known-good anchor (−27.6) and every recorded round-1/2 best** (their recorded worst-months −9.3/−13.4 were produced by the old convention, which runs ~2× milder on worst-months — same convention delta as the anchor's mean). The bar as written is miscalibrated for the canonical ruler; recalibrating or waiving it is JP's call. **Recommendation:** admit conditionally on the relative bar — beats every known best same-ruler (+2.11 vs anchor-net +0.62, vs avg-gated +1.46; t 1.41 vs 0.42/0.96 — highest honest t recorded for this seat) — with the −32.7 miss month registered as the seat's known 2021-mania liability; OR keep the bar and reject everything including the incumbent.

**Model-risk register (inherited + new):** (a) gate uses the Binance proxy — native-OKX gate agreement ~70% at settlement level (ledger 2026-10-18); mitigated by plateau + per-input robustness; native re-validation as OKX history accumulates. (b) bybit input materially weaker → gate value is input-specific; do not substitute inputs silently. (c) 2021-mania undercapture (above). (d) funding-cost proxy error ±0.26pts/mo on 1× (ledger) applies to all net numbers equally.

---

## 3. SECONDARY FINDING — funding-input quality is a real variable

Per-input law proved out: identical strategy, three inputs, same thresholds → bin +2.11 / avg +1.46 / byb +0.79 (t 0.38) at g0.7. Cross-venue funding disagreement is strategy-relevant, not noise. Worth one ledger line when the native OKX recorder has 12mo.

---

## 4. REJECTION LOG (all canonical, net of avg funding, full-grid grades)

| Config | mean %/mo | t | why rejected |
|---|---|---|---|
| raw turtle192 (anchor A2, net) | +0.62 | 0.42 | baseline, beaten by recruit |
| C_t192_byb_g0.5 / g0.7 | +0.24 / +0.79 | 0.11 / 0.38 | bybit gate input weak at BOTH own thresholds — input rejected |
| C_t192_avg_g0.5 / g0.7 | +1.50 / +1.46 | 0.78 / 0.96 | t < 1.0 bar |
| C_t192_bin_g0.5 | +1.76 | 1.01 | passes mean/t but dominated by g0.7 on plateau (worst −42.2 vs −32.7) |
| A_cb confirmed breakout N{144,192,288}×m{2} | −0.97…−0.66 | ≤ −0.38 | negative edge — m=2 hold catches falling knives |
| A_cb × m{3} (all N) | +0.15…+0.97 | ≤ 0.44 | t ≪ 1.0; worst window −65…−70; needs gate AND still fails |
| B_vol-scaled st{.004,.005,.006}×smin{.25,.5} | −0.49…+0.17 | ≤ 0.11 | flat edge; vol-sizing dilutes the fat tail that pays (confirms round-2 note) |
| D_washout K{30,60}×D{.20,.30} (NEW family) | −0.32…+0.34 | ≤ 0.2 | **mechanism failed**: recent washout marks ongoing bear, not post-capitulation restart; breakouts after washouts are not safer. Family closed. |
| Funding-gradient entry (round-2 F5) | — | — | not re-mined: inverted edge already documented |

---

## 5. REPRO

```
cd reports/bull_mining_r3
python3 lab.py anchor && python3 lab.py lanes && python3 lab.py mine   # substrate + canonical grades
python3 engine_check.py                                                # run_backtest + runner reality ratios
```
Read-only on repo (formula lives under this report dir; WQAlphaParams accepts absolute formula paths). MPLCONFIGDIR=/tmp/mpl; nice 10; runtime ~6 min total.
