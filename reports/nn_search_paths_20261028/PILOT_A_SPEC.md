# PILOT A — GBM RULE-EXTRACTOR FALSIFICATION PILOT (PRE-REGISTERED)

Frozen 2026-10-28 ~07:00 UTC, BEFORE any run. Author: DS subagent (nn-search-paths design brief).
Binding per AGENT_CONTRACT.md: no canonical performance number is produced by this pilot except
through `tools/screen_candidate.py`; AUC diagnostics are model diagnostics, not performance claims.
Kill numbers below are declared before execution and applied verbatim, whatever they say.

## Data & scope

- Primary: `framework/data_cache/okx_ETH_USDT_15m_20210101_20260928.csv` (ETH 15m OHLCV, ~195k bars).
- Conditioning: `fund_pct` injected exactly as `tools/screen_candidate.py` builds it
  (binance settled funding, 30d rolling pctl, via `tuner.alpha_orchestrator.build_fund_pct`).
- BTC 30d momentum (`f_btc30`) and ETH−BTC 30d relative strength (`f_rs30`) computed from
  `okx_BTC_USDT_15m_20210101_20260928.csv`, reindex-ffill to the ETH grid — **DIAGNOSTIC FEATURES
  ONLY** (no formula file can read BTC today; rules containing them are not screenable and are
  excluded from extraction; their share of surviving leaves is reported as the INJ-btc trigger).
- Exam span used: 2021-01-01 .. 2026-06-30. The sealed holdout (post-2026-06) is NOT read.

## Features (12, frozen)

| name | definition (all causal, end at close t) | screenable today |
|---|---|---|
| f_ret24 | ln(close/close.shift(96)) | yes |
| f_ret7d | ln(close/close.shift(672)) | yes |
| f_vol24 | rolling(96).std of 15m log returns | yes |
| f_atr | SMA(TR,96,min_periods=32)/close | yes |
| f_chan | (close−min(low,192).shift(1))/(max(high,192).shift(1)−min(low,192).shift(1)) | yes |
| f_disth | close/max(high,192).shift(1) − 1 | yes |
| f_fund | fund_pct (injected) | yes |
| f_volratio | f_vol24 / rolling(2016).std of 15m log returns | yes |
| f_tod_sin, f_tod_cos | sin/cos of 2π·(bar-of-day/96) | yes |
| f_btc30 | BTC ln(close/close.shift(2880)) | DIAGNOSTIC |
| f_rs30 | f_ret7d ETH − f_btc30 (30d versions) | DIAGNOSTIC |

## Labels (2 horizons, frozen)

Tradeable forward return: enter at `open[t+1]` (engine fill@next-open convention), exit at
`close[t+H]`: `y_H = 1 if close[t+H]/open[t+1] − 1 > 0.002 else 0` (cost hurdle = 2×8bp + ε).
- H = 96 bars (1 day)
- H = 672 bars (7 days)

Rows with any NaN feature or label dropped (warmup head, label tail).

## Splits (time-ordered, expanding walk-forward, NO shuffle, embargo = H)

| fold | train | valid |
|---|---|---|
| F1 | 2021-01-01 .. 2022-12-31 | 2023-01-01 .. 2023-12-31 |
| F2 | 2021-01-01 .. 2023-12-31 | 2024-01-01 .. 2024-12-31 |
| F3 | 2021-01-01 .. 2024-12-31 | 2025-01-01 .. 2026-06-30 |

Train rows with `t > valid_start − H` dropped (label embargo: no train label may peek into valid).

## Models (pre-registered ladder; sklearn only — lightgbm/torch ABSENT on this host)

- M0 base rate: P(y=1) per fold (reference line, not a model).
- M1 L1 logistic: `LogisticRegression(penalty="l1", solver="liblinear", C=0.1)` on standardized features.
- M2 GBM: `HistGradientBoostingClassifier(max_depth=3, max_iter=150, learning_rate=0.05,
  min_samples_leaf=500, l2_regularization=1.0, random_state=7)`.
- No M3 (tiny MLP): per the 2026-10-22 verdict, a net is strictly dominated by M2 at this scale;
  it enters only if M2 transfers and a capacity question actually arises. Not pre-registered here.

Metric: ROC AUC on train and valid, per fold × horizon × model. Base rate reported beside every AUC.

## KILL NUMBERS (applied verbatim)

- **K1 (extractor transfer — the single number that kills the path):**
  For M2: if, for BOTH horizons, median valid AUC over the 3 folds < **0.53** → path DEAD.
  Secondary pre-registered read: if (train AUC − valid AUC) > **0.15** in ≥ 2 of 3 folds for both
  horizons (memorization without transfer) → path DEAD even if the 0.53 median is barely met.
  The path survives only if ≥ 1 horizon clears median valid AUC ≥ 0.53 AND the gap rule holds for
  that horizon.
- **K2 (rule yield):** if extraction runs: 0 of the ≤10 extracted formulas passing
  `tools/screen_candidate.py` floors (mean>0, worst_abs≥−40, halves≥0, 2024+>0) → path DEAD at the
  rule level. Any passer is NOT a champion: it becomes an idea card with MINED-LINEAGE declared, and
  can never be seal-grade on extractor-seen data (confirmation requires untouched windows only).

## Extraction protocol (runs only if K1 passes; frozen now)

- Harvest leaf paths from every fold's M2 (surviving horizon only). Keep leaves with train leaf
  positive-rate ≥ **0.55** and support ≥ max(2000, 1% of fold train N).
- Drop any path containing a DIAGNOSTIC feature. Report the share of surviving leaves that were
  dropped for this reason (INJ-btc trigger: >50% → declared infra ask, operator approval required).
- Dedupe by rounded signature (feature set + thresholds rounded to 4 significant digits).
- Stability filter: signature must recur (same features, thresholds within ±15% relative) in ≥ 2 folds.
- Rank by valid-side precision (rule evaluated as boolean over that fold's valid window); keep ≤ **10**.
- Formula semantics (frozen): `pos = rule.astype(float)` (binary in/out, NO latch, NO smoothing,
  no extra params), warmup = 672+1 bars, imports numpy/pandas only, rolling ops only — must pass
  `tuner/validate_formula.py` AST+causality proof before any screen.

## CONTROL ARM — grammar enumeration (no learning; answers "does the GBM add anything?")

- Enumerate over the 10 screenable features: all 1-feature thresholds and all 2-feature conjunctions,
  thresholds at the fold-train quantiles {0.2, 0.4, 0.6, 0.8}, each side (above/below) allowed.
- Selection score (SELECTION ONLY — never reported as performance): valid-window arithmetic excess
  vs buy-hold with `pos.shift(1)·ret − 0.0008·|Δpos|`, same convention as the engine.
- Top **5** by selection score → validate_formula → screen_candidate, exactly once each.
- Pre-registered comparison: if the control arm's canonical outcomes ≥ the GBM arm's, the learned
  extractor adds nothing over dumb enumeration and the honest conclusion is "enumerate, don't learn."

## Multiple-testing accounting (declared now)

- All extracted/enumerated formulas belong to ONE pilot lineage: `NNPILOT-A-20261028` (formulas carry
  `# LINEAGE: NNPILOT-A-20261028` in the header). Lineage counted once in the program's generation
  ledger regardless of how many formulas it produced.
- H0 pass-rate prior: 0/≈190 graded candidates program-wide → p0 ≤ 1.5% (rule of three). E[false
  passes] = N_screened × p0, reported beside any pass. A pass is believable-pending-battery only if
  E[false passes] < 0.5 for the week's screened total.
- Both arms' passes go to the standard battery (jitter ±15%, retention, anchored v3.2, 2024+ door)
  BEFORE any further claim, and never to seal on extractor-seen data.

## Outputs (this directory only)

`diag_results.json` (AUC table + kill verdicts), `candidates/*.py` (formula files, full text also
appended to REPORT.md), `screen_results.txt` (verbatim screen_candidate output), screening staging
copies under `models/alpha_formulas/` are md5-recorded and REMOVED after screening (nothing outside
reports/ is committed by this pilot).
