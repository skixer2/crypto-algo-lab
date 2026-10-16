# Independent adversarial review — blender v2.1g (DeepSeek V4 Pro, 2026-10-16)

Reviewer: independent subagent, no sunk cost. Method: recompute-then-judge. All numbers below
were produced by scripts in `/tmp/dv_verify{1,2,3}.py` (rerunnable; repo untouched except this
report). Read-only discipline held; no exchange/bot contact.

Verification status of the "honest" stack as shipped:
- Arithmetic reproduction: **exact**. My recompose of ETH v2.1g from stored curves + detector 7
  gives mean_excess +7.3311%/mo vs official 7.3294 (Δ = 3dp weight renorm), t +2.961 vs 2.9607,
  windowed MDD 15.01 vs 15.008, FTX-2022-11 strat +22.15 vs +22.15, first/last windows exact.
- Data quality: clean. ETH 15m archive 201,217 rows, 0 dup timestamps, exactly 1 grid gap,
  0 OHLC violations, 0 non-positive prices. All 13 specialist curves perfectly aligned on a
  strict 15m grid ending 2026-07-28 (seal), positions numeric in {−1,0,+1}, zero NaN.
- Funding overlay: **reproduced** (sign + magnitude). rate × ffilled net-exposure, monthly sum:
  by-year pts {2021: 19.0 (their 19.1), 2022: 1.1 ✓, 2023: 3.2 ✓, 2024: 4.6 ✓, 2025: 1.7 ✓,
  2026: 0.8 (their 0.5)}, FTX-11-2022 +0.24 (their +0.2). Full-span mean drag 0.44 pts/mo vs
  their 0.33 (likely averaging-window difference; method script is not in the repo — see WARN-4).

---

## 1. FINDINGS

### CRITICAL-1 — The blend credits the router lane with the return of the bar that *triggers* it: one-bar lookahead is the entire edge

**Evidence (code):**
- `tools/blender.py:173-174` — `wl[mask] = W[li]` from `lane_of_bar[t]`, then
  `w_ret = (wl * rets.to_numpy()).sum(axis=1)` where `rets = eq.pct_change()`
  (blender.py `load_specialists`), i.e. lane computed on data ≤ close[t] is multiplied by the
  specialist return over (t−1, t].
- `tools/regime_grid.py:41-58` (`regime_array`) and `tools/blender.py:65-99` (`regime_series`):
  every lane condition (donchian mid, `below.rolling(confirm) ≥ 0.9`, Schmitt vr crossing,
  grind slope) is evaluated **including bar t's close**. Knowable only AT close[t].
- `framework/simulation.py` (equity semantics): position recorded at bar t is post-decision at
  close[t]; `rets_i[t+1] = eq[t+1]/eq[t]−1` is what that position earns. So a trader following
  the router rebalances at close[t] and earns rets_i[t+1]. The correct engine-consistent pairing
  is `wl[t]·rets[t+1] ≡ wl[t−1]·rets[t]`. The code as built uses `wl[t]·rets[t]`.

**Measured (ETH, 63 official windows, netted fees, detector 7):**

| variant | mean excess/mo | t | winMDD | contMDD |
|---|---|---|---|---|
| as-built `wl[t]·rets[t]` | **+7.33%** | +2.96 | 15.0% | 20.46% |
| honest `wl[t−1]·rets[t]` (pos lag1) | **−5.32%** | −2.47 | 30.6% | 95.1% |
| honest (pos as-is; fee-timing variant) | −5.29% | −2.46 | 30.6% | 95.0% |
| no-netted-fee as-built (fees embedded only) | +12.66% | — | — | — |

- Decomposition: as-built = honest + transition term. Transition bars (lane changed): 7,323 of
  195,265 (3.75%); their arithmetic contribution **+847% of notional over the span = +13.0
  pts/mo** — more than the whole claimed edge. Top-25 flip bars = 7.5% of |rent| (diffuse, not
  a few outliers).
- Mechanism confirmed: flip bars ARE the trigger bars. P(bench ret<0 | flip→bear bar) = 0.768
  vs 0.496 unconditional; mean bench ret on flip→expansion bars +0.53% vs +0.001% uncond.
  Threshold crossings (rolling-mean 0.9, vr 0.8, donchian mid) complete exactly on large moves.
- Case study (2026-03-23 11:00 UTC, biggest flip): bench +5.83% squeeze bar. Old lane =
  confirmed_bearish (alpha_035 short, rets −5.95%). As-built books the expansion lane on that
  bar → +0.0% (its specialists were flat). Honest books −5.86%. The "rent" is largely *dodging*
  the adverse move the old lane actually takes on the trigger bar.
- By-year mean excess as-built → honest (pts/mo): 2021 −5.4 → −21.2; 2022 +17.1 → +1.8;
  2023 −1.6 → −9.7; 2024 +4.5 → −5.1; 2025 +7.3 → −6.4; 2026 +17.3 → +0.9. The edge is rent in
  every period; no year survives.
- Falsification check on myself: shifting the WHOLE stream one bar (rets+pos shifted, lane kept)
  returns +7.44 — a pure relabel that still beats the real-time bench in monthly windows,
  proving the monthly stats are sensitive to stream alignment they shouldn't see.

**Scope of contamination:** every artifact produced by `evaluate()` or
`compose_transplant.py:83` — ETH official numbers (+7.33/+7.01, t 2.96, MDD 15.0/19.5),
SOL/BTC transplant composes (+13.87/+4.25 and all full-cost variants), fast-vs-direct portfolio
JSONs, all `v21g_*` graphs, **and the Optuna weight selection itself** (5,000 trials optimized
the biased objective; the weights are fitted to harvest flip-bar rent). The per-specialist
curve comparisons (chaos_ranking: fast=direct for 15/18) are engine-level and unaffected.
Specialists' own stats (e.g., alpha_050 lineage claims) are NOT affected by this finding.

**What would settle it fully:** re-run the 3000-trial blender under the honest pairing
(vectorized evaluate, same runtime as the original run — no engine re-sims needed). Cheaper
partial test already done: honest pairing with the shipped weights = −5.29%/mo.

### CRITICAL-2 — 1h bias bars are fed before they close (up to 60-min lookahead in alpha_056/032/004)

- `framework/simulation.py:162`: `while idx < len(ts_list) and ts_list[idx] <= ts:` feeds the
  bias-TF bar labeled ≤ ts. OKX/ccxt stamps are bar **open** time (verified: 1h bar 2026-06-01
  00:00 open == 15m 00:00 open). The 1h bar labeled 10:00 closes at 11:00 but is fed to the
  model from exec tick 10:00 — its close enters the bias EMA up to 60 min before it exists.
- Manifest params: `use_bias_filter=true` for alpha_056 (0.347 vol_compressed + 0.175 expansion
  — the heaviest vol-lane weight), alpha_032 (0.03), alpha_004 (0.047). Others false.
- Fix: feed bias bar only when `ts_list[idx] + bar_duration ≤ ts`. Re-sim 3 specialists on the
  fast path (~15 s each per ledger), recompose. Not re-simmed here (severity bounded: gates
  entries for 3 specialists; CRITICAL-1 dominates), but same bug class and must be fixed before
  any honest re-optimization.

### WARN-1 — Risk rails are anchored on a DD distribution that silently drops the worst episode

- Full-span continuous max DD of the as-built curve: **20.46%** (episode 2021-01-07 → 01-11,
  recovered 01-19) — *before* the first fitness window (Apr 2021). Apr-2021-anchored max:
  19.28% (2024-12-20 → 2025-02-01) — this matches the ledger's "max 19.5".
- Consequence: the v0 de-risk rail (20% continuous DD → halve) sits **0.46 pts below a
  historically realized drawdown** on the full-span curve, and the 25% kill rail has only
  ~4.5 pts headroom to the true backtest max. The "top-4 cluster 18.7–19.5%" in the ledger
  excluded Jan-2021 because the windows grid starts 2026-04-01. Rails are (correctly) marked
  PROVISIONAL; add the Jan-2021 episode to the ledger table before the pilot.
- Also: all four top episodes (20.46 / 19.28 / 18.97 / 18.81) are computed on the *rented*
  curve. Under an honest pairing the DD distribution is worse (contMDD 95%); rails must be
  re-derived after CRITICAL-1 fix, not just re-anchored.

### WARN-2 — t=2.96 is a best-of-5,000 in-sample statistic even before CRITICAL-1

- `blender_v21g_trials.json`: 5,000 trials, all non-vetoed; champion score 11.36 = max; trial
  mean-excess p99 = 7.21 vs champion 7.33; 38% of trials beat 7.33 on score. The 63 monthly
  windows are simultaneously the selection set and the reporting set (detector dim adds 48 more
  choices). Autocorrelation of monthly excess is −0.05 (naive t fine as a statistic), block-3
  bootstrap CI [+2.9, +11.9] — but all of this describes the rented stream. PBO/bootstrap
  conclusions from the v1b era do not carry over to v21g. Any post-fix evaluation needs
  walk-forward (train on trailing window, score forward) rather than full-span selection.

### WARN-3 — Fee stack charges two mutually exclusive cost models (arithmetic verified, policy flagged)

- Verified: `evaluate()` implements the JP netted law exactly as documented
  (`tools/blender.py:176-180`): `turn = |Δ(Σ w·pos)|`, `port_ret = w_ret − 0.0008·turn`;
  curves already embed per-specialist trade fees at 0.0008 (per-precompute docstring).
- Measured: embedded wedge per specialist over the span (gross pos·bench − curve): −4.6 to
  −125 pts (alpha_035: gross +39.8% → curve −85.0%, 549 position flips/mo at avg |pos| 0.61);
  netted layer adds −5.33 pts/mo on top (as-built). Net exposure sign-flips 59.6×/mo.
- The two layers model opposite worlds (13 separate books vs 1 netted book). Charging both is
  conservative but incoherent, and post-CRITICAL-1 it is decisive: honest gross (curves'
  embedded fees included) is ≈ +1.4%/mo arithmetic; the netted layer alone takes it to −5.3.
  Under the netted law's own logic the per-specialist embedded fees are ledger fiction and
  should be stripped via fee-free re-sims; alternatively keep per-specialist fees and drop the
  netted layer. Owner-decreed, so flag-only — but the choice changes the sign of the system.

### WARN-4 — Reproducibility gaps in the shipped audit trail

- The funding-overlay JSONs and `v21g_transplant_CORRECTED.json` were produced by scripts not
  present anywhere in the repo (searched; only `/tmp` ephemera). The overlay is scientifically
  load-bearing (7.33 → 7.01).
- Shipped `reports/audit_scripts_20261015/compose_transplant.py` still contains the guard
  criterion that the same audit diagnosed as wrong (full-month vs lane-restricted); re-running
  it today exits rc=3 at Nov-2022 (`INCONSISTENCY_{SOL,BTC}.json` are present), so the
  corrected SOL/BTC numbers cannot be regenerated from the shipped script.
- Window-grid mismatch: compose uses 64 monthly starts `2021-04-01..2026-07-01`
  (`compose_transplant.py:87`) vs the official blender's 63 (`tools/blender.py:248`) — the
  transplant means are not like-for-like with ETH's official stats.
- Stored weights 3dp (vol_compressed 1.001) is known; note it also means `evaluate()` on the
  shipped JSON requires renormalization — the ledger's compose-arithmetic workaround is
  correct, but the champion artifact is not directly reloadable.

### WARN-5 — Engine fill model: same-bar close fills and close-only SL/TP

- `simulation.py:155,168-183`: decisions and fills at the same close print; SL/TP evaluated on
  close only. Two consequences: (a) the class of "signal includes the fill bar's close" is
  systematic (specialists too — their entries fill at the close that generated them; a live
  book fills ≥ one print later); (b) intra-bar stop breaches never register — price can trade
  below stop and recover by close with no exit, which flatters crash weeks (compounds the
  known FTX fiction). Docstrings contradict (`simulation.py:54` says "check SL/TP against
  candle high/low"). Worth one bounded study: high/low stop variant for alpha_035/050 on
  2022-05/2022-11 slices.

### INFO

- **Dead specialists carry weight:** alpha_028 and alpha_029 never trade on ETH (position ≡ 0
  over 195k bars); alpha_028 still holds 0.18 of the expansion lane (real lane exposure ~0.82
  face) and inflates the parsimony count ("active: 12"). alpha_004 avg|pos| = 0.00.
- **July 2026 (inside seal, never reported):** bench +18.31, strat +8.9 → excess −9.41 — a
  strong-bull-month miss consistent with up_capture 0.09; relevant to the "bull seat" question
  the seal is waiting on. Aug–Sep 2026 truly untouched (curves end 07-28; guard verified).
- **Bench convention:** excess is vs price-only bench while the strategy pays funding
  (+0.44 pts/mo measured on its book). Vs a perp B&H (funding on 1.0 exposure, ~+1.3 pts/mo
  average), reported excess would shrink by roughly that spread — mostly a 2021-2024 effect
  (rates positive 84% of events).
- **t / MDD mechanics:** window MDD on 15m equity marks (misses intra-bar); months grid has no
  edge effects (63 full months, len<2 guard never fires); grid/bench timestamp alignment exact
  (searchsorted equality asserted); `up_b = (e1 and …)·100` in `window_metrics` is a confusing
  no-op (e1 > 0 always), harmless.
- **Capacity:** netted turnover ≈ 59× equity notional/mo, specialist-book gross ≈ 64×; at
  $1M equity ≈ $60-64M/mo vs ≈ $11B/mo average volume in this archive — not binding at
  current scale; the archive's volume column looks small vs real ETH-SWAP (~$10-30B/day), so
  treat as contract-scaled and re-check before sizing claims.
- **Position-parse class (the Oct-16 bug):** current stored curves are numeric and clean; the
  "parse coverage > 0" rule is right. Add it as an assert inside `evaluate()` too, not just
  compose (defence at the choke point).

---

## 2. NEW UNCERTAINTIES (beyond the known list)

1. Router pairing lookahead (CRITICAL-1) — invalidates all blend-level numbers.
2. Bias-TF feed lookahead (CRITICAL-2) — affects alpha_056/032/004 entries.
3. Full-span DD max 20.46% (Jan-2021) outside the fitness windows — rails anchor thinner than
   documented (WARN-1), and the whole DD distribution changes post-fix.
4. Selection depth: 5,000 trials + 48 detectors on the reporting windows (WARN-2).
5. Double fee-stack incoherence quantified: honest gross ≈ +1.4 pts/mo vs netted layer −5.3
   (WARN-3).
6. Close-only SL/TP + same-bar-close fill optimism class (WARN-5).
7. 64-vs-63 window compose inconsistency (WARN-4).
8. Bench is price-only while strategy pays funding (INFO).
9. Ephemeral audit scripts (WARN-4).
10. July-2026 in-seal bull-month miss, unreported (INFO).

## 3. PRIORITIZED IMPROVEMENTS

**P0 — before any further v21g-family work**
1. Fix the pairing: `port_ret[t] = wl[t−1]·rets[t]` (equivalently `wl[t]·rets[t+1]`), same in
   `compose_transplant.py:83`; regenerate ETH/SOL/BTC composes + graphs. Cost: minutes of CPU.
   Expected impact: replaces +7.33 with the honest baseline (≈ −5.3 with current weights).
2. Re-optimize weights under the honest objective (same vectorized evaluate, ~same wall time as
   the original 5,000-trial run). Everything else (funding overlay, slippage sweep, transfer,
   skill maps) re-runs only after this. Impact: the only numbers that can be trusted.
3. Fix the bias feed: `ts_list[idx] + Timedelta(tf) ≤ ts` in `simulation.py:162`; re-sim the 3
   affected specialists (fast path). Impact: removes a second lookahead from ~0.5 of weights.
4. Two permanent guards: (a) **flip-bar rent monitor** — assert transition-bar arithmetic
   contribution < 25% of gross (current: ~90%); (b) **relabel-invariance test** — shifting the
   strategy stream by one bar must move windowed mean excess by < ~1 pt (current: +0.11).
   Either would have caught CRITICAL-1 automatically.
5. Commit the funding-overlay + corrected-compose scripts into `reports/audit_scripts_*` and
   repoint the compose guard to lane-restricted returns (its own diagnosis).

**P1 — this cycle**
6. Re-derive risk rails on the honest full-span curve; add the Jan-2021 20.46% episode to the
   ledger; set the de-risk trigger below the historical p90, not near the max.
7. Decide the fee model (one book or 13) and re-price: strip embedded fees via fee-free re-sims
   (fast path, cheap) OR drop the netted layer. Impact: changes the sign of the honest system.
8. Bench: report excess vs perp total return (bench + funding on 1.0 exposure) next to the
   price-bench number.
9. Walk-forward the blend (fit trailing 2y → score forward) once the objective is honest; the
   v1b-era PBO≈0 does not transfer.
10. Drop alpha_028/029 from the pool or force their weights to 0 pre-search (pure dead weight;
   parsimony and transfer interpretability).

**P2 — research**
11. The detector's flip-bar information is real (post-flip bars keep the trigger-bar sign:
    −0.215%/+0.269% one bar after flips) — an honest objective can still monetize continuation;
    consider a "next-bar regime prediction" formulation instead of the concurrent label.
12. Bounded high/low stop study (alpha_035/050, 2022-05/2022-11) to bound close-only stop
    optimism before deployment sizing.
13. Cheaper test I could not afford: full next-bar-open-fill re-sims of all 13 specialists
    (14-160 min each on this box). The one-run version: re-sim alpha_035, alpha_050, alpha_056
    with one-bar-delayed fills, recompose honestly — bounds the specialist-level fill optimism.

---

## Executive summary

1. Reproduction of v2.1g arithmetic is exact (+7.3311 vs 7.3294; FTX +22.15; windows match) — the pipeline is internally consistent, but:
2. **CRITICAL: the blend pairs the router lane at bar t with the return that ENDED at bar t.** The lane is computed from close[t]; that return was earned by positions held since close[t−1]. One-bar lookahead.
3. Measured: honest pairing (wl[t−1]) flips +7.33%/mo (t 2.96) to **−5.29%/mo (t −2.46)**; windowed MDD 15→30.6%, continuous 20.5→95%.
4. The rent = +13.0 pts/mo from 3.75% of bars (lane-flip bars), spread over 7,322 events; flip bars are the threshold-crossing bars by construction.
5. By year, honest excess is negative in 4 of 6 years. The Optuna weights were selected under the biased objective — all blend-level artifacts (ETH/SOL/BTC, fast-vs-direct, graphs, +7.01 funding-included) need regeneration after the fix.
6. **CRITICAL #2: 1h bias bars feed before they close** (open-labeled OKX stamps, `ts<=ts` feed): alpha_056/032/004 see closes up to 60 min early. Fix: feed after bar completion.
7. WARN: true full-span continuous max DD is 20.46% (Jan-2021, outside fitness windows) vs documented 19.5 — the 20% de-risk rail sits below a realized episode; re-derive rails post-fix.
8. WARN: t=2.96 is best-of-5,000 trials × 48 detectors on the 63 reporting windows; PBO/bootstrap claims do not transfer. Fee stack charges both per-specialist and netted layers (honest gross ≈ +1.4 pts/mo vs netted −5.3) — pick one world.
9. Funding overlay reproduced independently (by-year exact to 0.1 pts); data quality clean; position-parse rule verified; capacity fine at ≤$1M.
10. New datum: July 2026 (in-seal, unused) excess −9.4 in a +18.3 bull month.
11. Top actions: (1) fix pairing, (2) re-optimize honestly, (3) fix bias feed, (4) add flip-bar-rent + relabel-invariance guards, (5) commit ephemeral audit scripts.
12. The detectors/specialists engine itself is not accused: per-specialist claims stand; the bug lives in the composition layer (blender.py:174, compose_transplant.py:83) and the bias feed (simulation.py:162).
