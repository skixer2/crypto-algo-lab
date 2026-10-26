# WQ-101 Verbatim Port + Screen — one-shot bounded experiment

**Date:** 2026-10-26 · **Requester:** JP (via main session) · **Executor:** subagent (glm-5.3-flash)
**Source:** Zura Kakushadze, *101 Formulaic Alphas*, arXiv:1601.00991 — formulas transcribed
character-for-character from the arXiv PDF (canonical source). Grading data: the canonical ETH
cache only (`framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv`); **no external data
was used for any number in this report.**
**Contract:** `AGENT_CONTRACT.md` + `models/alpha_formulas/README.md`. Every number below is
printed verbatim by `tools/screen_candidate.py` (stats_canonical ruler). No tuning, no variants,
no re-runs: each formula got exactly one screen run.

---

## 1. Portability census — 18 ported / 83 not portable (N=1)

**Rule applied (as briefed):** any formula whose core semantics require a cross-sectional panel
of instruments — `rank(x)` (cross-sectional rank), `scale(x, a)` (rescale so Σ|x| = a across
assets), `indneutralize(x, g)`, or the `cap` (market-cap) field — is **NOT-PORTABLE** at N=1.
Pure time-series formulas were ported VERBATIM in semantics.

**Result: 18 pure time-series formulas ported; 83 cross-sectional-essential formulas skipped.**

### 1a. Ported (Y = 18)

| File | Original (verbatim) | tanh-bound deviation? |
|---|---|---|
| wq101_006.py | `(-1 * correlation(open, volume, 10))` | no (bounded) |
| wq101_007.py | `((adv20 < volume) ? ((-1 * ts_rank(abs(delta(close, 7)), 60)) * sign(delta(close, 7))) : (-1 * 1))` | no (bounded) |
| wq101_009.py | `((0 < ts_min(delta(close, 1), 5)) ? delta(close, 1) : ((ts_max(delta(close, 1), 5) < 0) ? delta(close, 1) : (-1 * delta(close, 1))))` | YES |
| wq101_012.py | `(sign(delta(volume, 1)) * (-1 * delta(close, 1)))` | YES |
| wq101_021.py | `((((sum(close, 8) / 8) + stddev(close, 8)) < (sum(close, 2) / 2)) ? (-1 * 1) : (((sum(close, 2) / 2) < ((sum(close, 8) / 8) - stddev(close, 8))) ? 1 : (((1 < (volume / adv20)) \|\| ((volume / adv20) == 1)) ? 1 : (-1 * 1))))` | no (±1) |
| wq101_023.py | `(((sum(high, 20) / 20) < high) ? (-1 * delta(high, 2)) : 0)` | YES |
| wq101_024.py | `((((delta((sum(close, 100) / 100), 100) / delay(close, 100)) < 0.05) \|\| (… == 0.05)) ? (-1 * (close - ts_min(close, 100))) : (-1 * delta(close, 3)))` | YES |
| wq101_026.py | `(-1 * ts_max(correlation(ts_rank(volume, 5), ts_rank(high, 5), 5), 3))` | no (bounded) |
| wq101_035.py | `((Ts_Rank(volume, 32) * (1 - Ts_Rank(((close + high) - low), 16))) * (1 - Ts_Rank(returns, 32)))` | no (bounded) |
| wq101_041.py | `(((high * low)^0.5) - vwap)` | YES |
| wq101_043.py | `(ts_rank((volume / adv20), 20) * ts_rank((-1 * delta(close, 7)), 8))` | no (bounded) |
| wq101_046.py | `((0.25 < (((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10))) ? (-1 * 1) : (((… ) < 0) ? 1 : ((-1 * 1) * (close - delay(close, 1)))))` | YES |
| wq101_049.py | `(((((delay(close, 20) - delay(close, 10)) / 10) - ((delay(close, 10) - close) / 10)) < (-1 * 0.1)) ? 1 : ((-1 * 1) * (close - delay(close, 1))))` | YES |
| wq101_051.py | same construct as #49 with threshold `(-1 * 0.05)` | YES |
| wq101_053.py | `(-1 * delta((((close - low) - (high - close)) / (close - low)), 9))` | YES |
| wq101_054.py | `((-1 * ((low - close) * (open^5))) / ((low - high) * (close^5)))` | YES |
| wq101_084.py | `SignedPower(Ts_Rank((vwap - ts_max(vwap, 15.3217)), 20.7127), delta(close, 4.96796))` | YES |
| wq101_101.py | `((close - open) / ((high - low) + .001))` | no (bounded) |

### 1b. NOT-PORTABLE (X = 83) — one-line reason each

Primary blocker listed per formula; "rank" = cross-sectional rank (the dominant blocker —
75 of 83 also/only need it), "scale" = cross-sectional rescale, "indn" = indneutralize /
IndClass groups, "cap" = market-cap field (absent from a single-asset crypto panel).

| Alpha | Blocker (why it cannot live at N=1) |
|---|---|
| 1 | `rank(Ts_ArgMax(SignedPower(...), 5))` — cross-sectional rank |
| 2 | `correlation(rank(...), rank(...), 6)` — ranks of two series, cross-asset |
| 3 | `correlation(rank(open), rank(volume), 10)` — cross-sectional ranks |
| 4 | `Ts_Rank(rank(low), 9)` — rank(low) is cross-sectional |
| 5 | `rank(open − SMA(vwap,10)) · abs(rank(close − vwap))` — cross-sectional ranks |
| 8 | `rank(...)` of a delayed open/returns product |
| 10 | Alpha#9 wrapped in cross-sectional `rank(...)` |
| 11 | three `rank(...)` terms (ts_max/ts_min/delta) |
| 13 | `rank(covariance(rank(close), rank(volume), 5))` |
| 14 | `rank(delta(returns, 3))` multiplied by a TS correlation |
| 15 | `sum(rank(correlation(rank,rank)), 3)` |
| 16 | `rank(covariance(rank(high), rank(volume), 5))` |
| 17 | `rank(ts_rank(close)) · rank(dd(close)) · rank(ts_rank(vol/adv20))` |
| 18 | `rank(stddev(abs(c−o)) + (c−o) + correlation(...))` |
| 19 | `rank(1 + sum(returns, 250))` |
| 20 | three `rank(...)` of open vs delayed H/L/C |
| 22 | `delta(correlation(...), 5) · rank(stddev(close, 20))` |
| 25 | `rank((−returns · adv20 · vwap · (high − close)))` |
| 27 | `0.5 < rank(sum(correlation(rank,rank)))` threshold on cross-rank |
| 28 | `scale(correlation(adv20, low, 5) + mid − close)` — cross-sectional rescale |
| 29 | rank/scale/product ladder (`scale(log(sum(ts_min(rank(rank(...))))))`) |
| 30 | `1 − rank(sign-momentum sum)` |
| 31 | `rank(rank(rank(decay_linear(...))))` ladder + `scale(...)` |
| 32 | `scale(...)` ×2 |
| 33 | `rank(−(1 − open/close))` |
| 34 | `rank(1 − rank(stddev ratio)) + rank(1 − rank(delta))` |
| 36 | five `rank(...)` terms (weighted sum) |
| 37 | `rank(correlation(delay(open−close), close, 200)) + rank(open−close)` |
| 38 | `rank(Ts_Rank(close, 10)) · rank(close/open)` |
| 39 | `rank(delta · (1 − rank(decay_linear(vol/adv20)))) · (1 + rank(sum(returns, 250)))` |
| 40 | `rank(stddev(high, 10)) · correlation(high, volume, 10)` |
| 42 | `rank(vwap − close) / rank(vwap + close)` |
| 44 | `correlation(high, rank(volume), 5)` — rank(volume) is cross-sectional operand |
| 45 | `rank(SMA(delay(close))) · corr · rank(correlation(SMA5, SMA20))` |
| 47 | `rank(1/close) · volume/adv20 · ... − rank(vwap − delay(vwap))` |
| 48 | `indneutralize(..., IndClass.subindustry)` |
| 50 | `ts_max(rank(correlation(rank(volume), rank(vwap))), 5)` |
| 52 | `rank((sum(returns,240) − sum(returns,20))/220)` |
| 55 | `correlation(rank((close − ts_min)/(ts_max − ts_min)), rank(volume), 6)` |
| 56 | `rank(...) · rank(returns · cap)` — rank + **cap** unavailable |
| 57 | `(close − vwap) / decay_linear(rank(ts_argmax(close, 30)), 2)` |
| 58 | `IndNeutralize(vwap, IndClass.sector)` |
| 59 | `IndNeutralize(vwap-combo, IndClass.industry)` |
| 60 | `scale(rank(...))` ×2 |
| 61 | `rank(vwap − ts_min(vwap)) < rank(correlation(vwap, adv180))` |
| 62 | `rank(correlation) < rank(rank(open)+rank(open) < ...)` — rank ladder |
| 63 | `rank(decay(delta(IndNeutralize(close)))) − rank(decay(correlation(...)))` |
| 64 | `rank(corr) < rank(delta(vwap-combo))` |
| 65 | `rank(corr(open-combo, sum(adv60))) < rank(open − ts_min(open))` |
| 66 | `rank(decay_linear(delta(vwap))) + Ts_Rank(decay_linear(...))` |
| 67 | `rank(high − ts_min) ^ rank(corr(IndNeutralize, IndNeutralize))` — rank + indn |
| 68 | `Ts_Rank(corr(rank(high), rank(adv15))) < rank(delta(...))` |
| 69 | `rank(ts_max(delta(IndNeutralize(vwap)))) ^ Ts_Rank(corr)` — rank + indn |
| 70 | `rank(delta(vwap)) ^ Ts_Rank(corr(IndNeutralize(close), adv50))` — rank + indn |
| 71 | `Ts_Rank(decay(corr(Ts_Rank, Ts_Rank))) vs Ts_Rank(decay(rank(...)^2))` |
| 72 | `rank(decay(corr)) / rank(decay(corr))` |
| 73 | `max(rank(decay(delta(vwap))), Ts_Rank(decay(...)))` |
| 74 | `rank(corr(close, sum(adv30))) < rank(corr(rank-combo, rank(volume)))` |
| 75 | `rank(corr(vwap, volume)) < rank(corr(rank(low), rank(adv50)))` |
| 76 | `max(rank(decay(delta)), Ts_Rank(decay(Ts_Rank(corr(IndNeutralize(low))))))` — rank + indn |
| 77 | `min(rank(decay(...)), rank(decay(corr(mid, adv40))))` |
| 78 | `rank(corr(low-combo, sum(adv40))) ^ rank(corr(rank(vwap), rank(volume)))` |
| 79 | `rank(delta(IndNeutralize(open/close combo))) < rank(corr)` — rank + indn |
| 80 | `rank(Sign(delta(IndNeutralize(...)))) ^ Ts_Rank(corr(high, adv10))` — rank + indn |
| 81 | `rank(Log(product(rank(rank(corr)^4)))) < rank(corr(rank(vwap), rank(volume)))` |
| 82 | `min(rank(decay(delta(open))), Ts_Rank(decay(corr(IndNeutralize(volume)))))` — rank + indn |
| 83 | `rank(delay((high−low)/SMA5)) · rank(rank(volume))` |
| 85 | `rank(corr(high/close-combo, adv30)) ^ rank(corr(Ts_Rank, Ts_Rank))` |
| 86 | `Ts_Rank(corr(close, sum(adv20))) < rank((open+close) − (vwap+open))` |
| 87 | `max(rank(decay(delta)), Ts_Rank(decay(abs(corr(IndNeutralize(adv81))))))` — rank + indn |
| 88 | `min(rank(decay(rank ladder)), Ts_Rank(decay(corr(Ts_Rank, Ts_Rank))))` |
| 89 | `Ts_Rank(decay(corr(...))) − Ts_Rank(decay(delta(IndNeutralize(vwap))))` — indn |
| 90 | `rank(close − ts_max) ^ Ts_Rank(corr(IndNeutralize(adv40), low))` — rank + indn |
| 91 | `Ts_Rank(decay(decay(corr(IndNeutralize(close))))) − rank(decay(corr))` — indn + rank |
| 92 | `min(Ts_Rank(decay(bool)), Ts_Rank(decay(corr(rank(low), rank(adv30)))))` |
| 93 | `Ts_Rank(decay(corr(IndNeutralize(vwap)))) / rank(decay(delta))` — indn + rank |
| 94 | `rank(vwap − ts_min) ^ Ts_Rank(corr(Ts_Rank(vwap), Ts_Rank(adv60)))` |
| 95 | `rank(open − ts_min) < Ts_Rank(rank(corr(...))^5)` |
| 96 | `max(Ts_Rank(decay(corr(rank(vwap), rank(volume)))), Ts_Rank(decay(Ts_ArgMax(corr))))` |
| 97 | `rank(decay(delta(IndNeutralize(...)))) − Ts_Rank(decay(Ts_Rank(corr)))` — rank + indn |
| 98 | `rank(decay(corr(vwap, sum(adv5)))) − rank(decay(Ts_Rank(Ts_ArgMin(corr(rank,rank)))))` |
| 99 | `rank(corr(mid, sum(adv60))) < rank(corr(low, volume))` |
| 100 | `scale(indneutralize(indneutralize(rank(...)))) · (volume/adv20)` — scale + indn + rank |

---

## 2. Port conventions (identical in all 18 files, declared in each header)

- `returns = close.pct_change()`; `delay(x,d) = x.shift(d)`; `sign = np.sign`;
  `correlation(x,y,d) = x.rolling(d).corr(y)` (time-serial, per appendix);
  `stddev/sum/ts_min/ts_max = rolling(d)`; `ts_rank = trailing percentile rank in (0,1]`.
- `vwap = (high+low+close)/3` — bar-level proxy (paper's vwap is a daily field).
- `adv{d} = (close·volume).rolling(d).mean()` — dollar-volume per the appendix, with `d`
  counted in **15m bars, not days** (declared N=1 unit deviation, inherent to the panel).
- **The only permitted adaptation:** where a formula's raw output is unbounded
  (price-unit spreads/exponents), output = `np.tanh(raw / |rolling_std(raw)|)`,
  window 480 bars (min_periods 96); degenerate σ → flat 0 (wrapper fillna(0) convention).
  Bounded formulas (correlations, ts_ranks, ±1 ladders, #101) were left untouched.
  Flagged "YES" in table 1a; every such case is restated in the file's header.
- Numeric hygiene (declared, not semantic): #53/#54 map undefined divisions
  (0-range bars exist in the cache: 68 `high==low`, 3561 `close==low`) to NaN;
  #84 maps ±inf overflow from `x**a` to NaN. Never extrapolated.
- Validation: `tuner/validate_formula.py` PASS ×18 (one retry: #53 needed the
  degenerate-σ guard in the shared `_bound`; all others passed first try).

## 3. Canonical screen — verbatim numbers (stats_canonical ruler, long-only engine convention)

Ran 2026-10-26, one run each, `nice -n 10`, MPLCONFIGDIR=/tmp/ml. **Verbatim output of
`tools/screen_candidate.py`** (stats_canonical ruler; long-only engine convention:
decide@close, fill@next open, fee 0.0008 netted on |Δpos|, buy-hold bench).

| file | mean_excess %/mo | t | DD % | worst_abs_month % | halves (H1/H2, %sum) | 2024+ %/mo | mean>0 | worst>=-40 | halves>=0 | 2024+>0 | verdict |
|---|---|---|---|---|---|---|---|---|---|---|---|
| wq101_006 | -18.74 | -7.87 | -100.0 | -29.3 | -585.3/-624.9 | -19.13 | FAIL | PASS | FAIL | FAIL | FAIL |
| wq101_007 | -1.85 | -0.67 | 0.0 | +0.0 | +0.0/+0.0 | -2.58 | FAIL | PASS | PASS | FAIL | FAIL |
| wq101_009 | — | — | — | — | — | — | — | — | — | — | **NO NUMBER: grade aborted** (see 3b) |
| wq101_012 | — | — | — | — | — | — | — | — | — | — | **NO NUMBER: grade aborted** (see 3b) |
| wq101_021 | -28.39 | -13.27 | -100.0 | -49.6 | -939.1/-1061.7 | -29.22 | FAIL | FAIL | FAIL | FAIL | FAIL |
| wq101_023 | -22.75 | -8.18 | -100.0 | -32.7 | -833.2/-764.0 | -22.42 | FAIL | PASS | FAIL | FAIL | FAIL |
| wq101_024 | -2.53 | -0.91 | -37.9 | -5.3 | -23.6/-15.4 | -3.03 | FAIL | PASS | FAIL | FAIL | FAIL |
| wq101_026 | -12.89 | -4.92 | -100.0 | -22.2 | -388.4/-394.1 | -13.22 | FAIL | PASS | FAIL | FAIL | FAIL |
| wq101_035 | -28.93 | -12.56 | -100.0 | -40.0 | -1038.1/-1076.0 | -29.39 | FAIL | PASS | FAIL | FAIL | FAIL |
| wq101_041 | — | — | — | — | — | — | — | — | — | — | **NO NUMBER: grade aborted** (see 3b) |
| wq101_043 | -37.37 | -17.05 | -100.0 | -51.0 | -1431.2/-1478.0 | -37.60 | FAIL | FAIL | FAIL | FAIL | FAIL |
| wq101_046 | -26.39 | -12.23 | -100.0 | -45.3 | -1017.4/-901.4 | -25.62 | FAIL | FAIL | FAIL | FAIL | FAIL |
| wq101_049 | -38.24 | -15.34 | -100.0 | -49.9 | -1550.0/-1524.4 | -38.26 | FAIL | FAIL | FAIL | FAIL | FAIL |
| wq101_051 | -37.81 | -15.28 | -100.0 | -50.0 | -1527.3/-1501.0 | -37.82 | FAIL | FAIL | FAIL | FAIL | FAIL |
| wq101_053 | -18.07 | -6.54 | -100.0 | -25.1 | -588.0/-635.0 | -19.36 | FAIL | PASS | FAIL | FAIL | FAIL |
| wq101_054 | -1.85 | -0.67 | 0.0 | +0.0 | +0.0/+0.0 | -2.58 | FAIL | PASS | PASS | FAIL | FAIL |
| wq101_084 | -1.85 | -0.67 | -0.1 | +0.0 | +7.6/+0.0 | -2.58 | FAIL | PASS | PASS | FAIL | FAIL |
| wq101_101 | -52.42 | -19.67 | -100.0 | -60.3 | -2334.8/-2512.3 | -54.16 | FAIL | FAIL | FAIL | FAIL | FAIL |

Raw per-file outputs (exact stdout): `reports/wq101_verbatim_screen/screens/wq101_NNN.txt`.

Reading notes (no re-computation, ruler numbers above are the only numbers):
- The three near-flat rows (007, 054, 084) are alphas whose verbatim semantics barely go long
  on this panel (007: `adv20 < volume` with dollar-volume adv is almost never true; 054/084:
  raw ≤ 0 dominates → long-only clip ≈ flat) — their −1.85%/mo is the buy-hold drift against
  a flat book, not active losses.
- The −100.0% DDs are genuine slow-bleed equity underflow to 0.0 across ~200k 15m bars,
  not a data artifact (worst bar in the canonical cache is −13.8%, 2023-08-17 21:30 UTC;
  no bar below −50% exists).

### 3b. Grader-refused screens (no canonical number exists — quoted verbatim)

Per AGENT_CONTRACT.md, only `stats_canonical`-printed numbers exist; these three runs were
**aborted by the ruler's own plausibility trap before any grade was printed** (no tuning, no
re-run — recorded as NO-NUMBER):

```
wq101_009: AssertionError: implausible window value -104.5% — unit mix suspected
wq101_012: AssertionError: implausible window value -102.0% — unit mix suspected
wq101_041: AssertionError: implausible window value -108.2% — unit mix suspected
```

(all three at `stats_canonical.py:47 _boundary_pct`, i.e. a monthly strategy-vs-bench excess
window steeper than −100%: a deep strategy drawdown month against a strongly positive bench
month. The trap is the canonical anti-unit-mix guard; its refusal is reported, not worked
around.) These three are precisely the fast sign-flipping price-delta alphas (#9/#12/#41).

## 4. Floor-passers

**NONE. 0 of 18 ported formulas pass any full floor set; 0 of 15 graded pass `mean>0`;
15/15 graded FAIL, 3/18 refused by the grader. There is nothing to flag for the exam.**

## 5. Verdict — does the 101 transfer to crypto 15m?

1. Structurally, no: 83/101 alphas are cross-sectional machinery (rank/scale/indneutralize/cap)
   and cannot exist at N=1 even in principle.
2. Semantically, the 18 pure time-series cores port cleanly (18/18 validation PASS, causality
   proven) — transcription is not the bottleneck.
3. Economically, they do not transfer: 15/15 graded fail every floor at 15m under the canonical
   long-only convention (mean excess −1.85 to −52.42 %/mo), and the 3 sign-flipping scalpers are
   so adverse the grader's trap refuses them.
4. The failure mode is uniform, not idiosyncratic — daily-horizon reversal/momentum logic run at
   15m bleeds fee-plus-adverse-selection until equity underflows; the near-flat rows show the
   rest of the library's edge (if any) lives in the short leg or in cross-sectional relative
   value, both outside this engine's lane.
5. Per brief, no tuning, variants, or rescue re-runs were attempted; the library as written is
   a dead end for ETH 15m — any further use would be a redesign, i.e. a new proposal.
