# Bull-Mining Round 2 — Expansion-Lane Recruitment Report

**Date:** 2026-10-19 · **Miner:** DeepSeek V4 Pro subagent (round 2) · **Symbol:** ETH/USDT
**Engine:** honest engine per 2026-10-18 laws (decisions at bar close, fills at NEXT bar open, close-evaluated SL/TP, catastrophic intrabar stop at 2× distance, gap-aware, bias candles post-completion).
**Engine validation:** harness copy (`honest_lab.HonestEngine`, fill_lag=1) reproduces `framework/simulation.py` equity to **max |diff| = 0.0 over 195,265 bars** on the turtle192 baseline before any mining run. `framework/`, `tools/`, `tuner/`, `models/`, `data/` untouched (read-only).
**Fee law:** standalone own-trade fees 0.0008/side. Funding cost is NOT inside the engine equity; it is accounted separately per settlement (long pays positive funding, exposure-weighted) and reported both gross and net.

---

## 1. Baseline recompute (bar to beat)

63-month grid 2021-04..2026-06, fixed spec, full-span continuous curves, funding-percentile = causal 30d rolling (90 settlements, **no bfill**), averaged Binance-proxy+Bybit input:

| spec | mean %/mo | t | worst mo | maxDD | time-in | funding paid %/mo | net %/mo |
|---|---|---|---|---|---|---|---|
| turtle192 raw (close>192-high; exit close<192-low−1·ATR96) | **+2.36** | 1.29 | −21.1 | — | 48% | — | — |
| turtle192 + gate fpct<0.5 (averaged) | **+2.92** | **1.81** | −13.4 | 42.8% | 31% | 0.31 | +2.61 |

⚠️ **Baseline discrepancy:** the brief recorded +1.12/mo (t 0.77) raw and +1.67 (t 0.87) gated. My validated harness gives **higher** numbers; the exact round-1 variant (harness predating the 2026-10-18 honest rebuild) could not be reproduced bit-for-bit. I adopt the **stricter self-confirmed numbers** (+2.36 raw / +2.92 gated, t 1.81) as the bar — any recruit passing here also clears the recorded baseline. Character check passes: gated latch = 167 round trips (2.4/mo), mean hold 3.7 days — a true latch, consistent with round-1's 5.6/mo ungated.

---

## 2. Protocol

- **Declared small grids** (fixed before grading): F1 pullback θ{30,35,40}×exitEMA{100,200}; F2 vol-scale σt{.004,.005,.006}×smin{.25,.5}; F3 confirm-breakout N{96,144,192}×hold m{2,4}; F4 momentum θ{.5,.75,1.0}×exit{mom,turtle}; F5 funding-gradient g{.5,.6,.7}×slope k{9,21}; G2 volgate σt{.005,.006}×smin{0,.25}×g{.5,.7}; G3 cbgate N{96,144,192}×g{.5,.7}×σt{.005,.006} (m=2, smin=.25). Each combo run ONCE full-span 2021-01..2026-07-28 (seal respected; July-2026 partial disclosed separately).
- **Nested walk-forward (selection objective):** for each month, pick argmax of trailing ≤12-month mean (fallback = declared grid center when trailing evidence ≤0 or <3 months); grade ONLY the unseen month → 63 unseen grades. Pick sequences saved (`_runs/picks_*.csv`).
- **Acceptance bar:** OOS mean ≥ +0.8%/mo over ≥8 unseen windows; OOS t ≥ 1.0; both OOS halves ≥ 0; no window > 50% of total excess; continuous DD ≤ 50%; worst OOS month ≥ −15%. Jitter: ±15% on ALL numeric params, 2 draws, sign never flips, OOS stays positive. Flip-rent: shift-0 vs shift-1; retention: shift-2.

---

## 3. RECRUIT — G3 "time-confirmed breakout × vol-scaled size × funding gate" (cbgate)

**Formula (15m exec bars, all causal):**
- Entry (decision at close t, fill t+1 open): `close_t > max(high, N)_trailing` **for the m-th consecutive close** (run counter over `close > trailing-N-high`), AND averaged-funding 30d-percentile `fpct_t < g` (causal, no bfill).
- Size: `clip(σ_target / σ_t, 0.25, 1.0)`, σ_t = ATR96/close (Wilder).
- Stops: disaster SL = entry − 4·ATR96 (engine's 2× catastrophic intrabar = 8·ATR backstop); no TP (sentinel c×10).
- Exit: `close < min(low, N)_trailing − 1.0·ATR96` (turtle exit, fills next open).

**Ship variants (plateau, not grid-max):** center `N=144, m=2, g=0.5, σt=0.005` and modal (WF's most-picked) `N=192, m=2, g=0.7, σt=0.005`. The g=0.7 column dominates g=0.5 in all 6 N×σt cells; N=144 tops both g columns; σt=0.006 ≥ 0.005 everywhere.

**OOS evidence (63 unseen months):**

| series | mean %/mo | t | H1 / H2 | worst | conc | DD |
|---|---|---|---|---|---|---|
| **WF-selected** | **+2.98** | **2.05** | +3.37 / +2.59 | −12.4% | 0.23 | 33.5% |
| fixed center (N144,g0.5) | +2.59 | 2.07 | — | −8.9% | — | 29.5% |
| fixed modal (N192,g0.7) | +2.86 | 2.12 | — | −9.3% | — | 26.2% |

**Acceptance checklist:** mean ✓ (3.7× bar) · ≥8 windows ✓ (63) · t ✓ (2.05) · halves ✓ · conc ✓ (0.23<0.5) · DD ✓ (33.5%≤50) · worst ✓ (−12.4≥−15). **ALL PASS — first candidate of the program with t>2 on the honest engine.**

**Guards:**
- Jitter ±15% (all numerics): center → +2.82 (t 2.37) / +3.26 (t 2.31); modal → +2.68 (t 2.13) / +3.12 (t 2.21). Sign never flips; OOS positive; no knife-edge.
- Flip-rent: shift0−shift1 = +0.002 (center) / +0.004 (modal) %/mo → **<0.3% of the edge**; shift-2 retention 96.8% / 92.3%.
- Funding gate trained per-input (threshold never imported): binance-only +3.19 (t 2.26); bybit-only +1.88 (t 1.76); averaged +2.86 (t 2.12) — **plateau across all three inputs**.
- Funding cost paid: 0.23–0.29 %/mo (time-in 23–24%, 1.7–1.9 entries/mo, 113–126 trades). **Net of funding: +2.36 (center) / +2.57 (modal) %/mo.**
- July-2026 partial (to seal 07-28, not part of the 63): center +0.2%, modal −1.9% vs B&H +20.4% — latches lag vertical months; disclosed, not graded.

**vs baselines:** beats recorded baseline (+1.12/+1.67) by 1.8–2.7×. vs **strict recomputed** gated incumbent (+2.92, t 1.81, worst −13.4, DD 42.8, net +2.61): WF series beats on mean AND t (+2.98/t 2.05); fixed modal is par on mean (+2.86), better t, **half the tail risk** (worst −9.3 vs −13.4; DD 26% vs 43%), par funding-net (+2.57 vs +2.61), monthly corr **0.73** → a genuine second earner for the bull seat, not a re-skin of the turtle.

## 4. BENCH (near-miss, not recruited) — G2 "vol-scaled turtle × funding gate"

WF OOS +2.69/mo, t 1.71, halves +3.47/+1.91, conc 0.28, DD 41.7% — but **worst month −17.4% fails the −15% bar** (Dec-2025-type crash enters at full size because σ is still low at the breakout). Fixed center +2.49/t 1.73, worst −11.4, DD 38.1, net +2.22. Note: smin floor never binds in practice (no entry bars in the size<0.25 regime) — sizing engages only from the top of the vol range. Kept as bench; a mid-position vol-de-risk would need engine support (partial resizing) that does not exist yet.

---

## 5. REJECTION LOG (feeds the failure ledger)

| family | spec tried | WF OOS | cause of death |
|---|---|---|---|
| **F1 pullback-in-trend** | 1h EMA50>EMA200 & close>EMA200 (causal merge) + 15m RSI(14) dip-recovery cross θ∈{30,35,40}, exit 15m EMA{100,200} | **−2.60/mo, t −3.65**, halves −0.5/−4.7, DD 87% | dip-buying inside "confirmed" 1h uptrends has NEGATIVE forward edge at 15m; confirmations arrive after the bounce is gone. Confirms round-1: expansion lane longs have no unconditional edge. |
| **F2 vol-scaled turtle (no gate)** | turtle192 with size=clip(σt/σ,.25,1), σt∈{.004,.005,.006} | +2.23/mo, t 1.33, worst **−19.3 FAIL**, DD 48.9 | vol-sizing without a funding gate still rides crowded-funding crashes at ≥25% size; below gated incumbent everywhere. |
| **F3 time-confirmed breakout, alone** | m-consecutive closes above trailing N-high (N∈{96,144,192}, m∈{2,4}), turtle exit | +1.22/mo, t 0.83, worst **−22.0 FAIL**, conc 0.57 FAIL | follow-through hold thins entries but does not fix the tail; needs the funding gate (→ became G3). *Disclosure: first F3 pass was invalidated by a class-definition bug (silently degraded to a turtle N-sweep); numbers above are post-fix.* |
| **F4 multi-horizon momentum** | mean of z-scored 8h/24h/96h returns > θ, exit score<0 or turtle | +1.55/mo, t 0.98, worst **−23.2 FAIL**, DD 54.7 FAIL | blended momentum confirms late in the move; crash months hit at full size; t<1 too. |
| **F5 funding-gradient entry** | turtle192 entry AND fpct rising over k∈{9,21} settlements while fpct<g∈{.5,.6,.7} | **−0.45/mo, t −0.49**, H2 negative | "crowd building, not crowded" is NOT a long edge — rising funding marks late-cycle; entry conditioning inverts the round-1 gate's benefit. |

**Known dead ends respected (not revisited):** composite/convolution latches with conviction multipliers; unconditional expansion-lane longs; anything needing same-bar fills. **No live processes touched; two trading bots undisturbed.**

## 6. Harness notes

- Files (all writes inside `reports/bull_mining_r2/`): `honest_lab.py` (engine copy + models + funding tools), `run_mining.py` (stages: validate|grids|wf|guards), `_runs/` (curves, monthly tables, picks, guard JSONs). Repro: `python3 run_mining.py grids && python3 run_mining.py wf`.
- Pitfall recorded: pandas 2.x parses these CSVs as datetime64[µs] — all timestamps force-normalized to ns (`to_ns`); µs/ns mixing silently zeroed funding accounting and stale-dated a 1h merge before the fix.
- Funding data: averaged Binance-proxy+Bybit (robust default); per-input plateau verified for the recruit.

---

## Executive summary (≤15 lines)

1. **1 recruit, full acceptance pass: G3_cbgate** — entry = m=2 consecutive 15m closes above their trailing N-high, funding-percentile gate (<0.5 center / <0.7 modal), size = clip(0.005/ATR96%, .25, 1), turtle exit (N-low − 1·ATR96).
2. WF-selected OOS (63 unseen months, honest engine, fees in): **+2.98%/mo, t 2.05**, halves +3.37/+2.59, worst −12.4%, conc 0.23, stitched DD 33.5% — first program candidate with t>2.
3. Beats the recorded round-1 baseline (+1.12/+1.67) by 1.8–2.7×; matches/beats my stricter recomputed incumbent (+2.92, t 1.81) with HALF its tail (worst −9.3 vs −13.4; DD 26% vs 43%) and corr 0.73 → true second earner.
4. Guards clean: jitter ±15% stays +2.7..+3.3 (t≥2.1); flip-rent <0.3% of edge; shift-2 retention 92–97%; gate plateau on Binance-only/Bybit-only/averaged inputs (never cross-imported).
5. Funding paid 0.23–0.29%/mo (23% time-in) → net +2.36..+2.57%/mo. July-2026 partial (ungraded): −1.9..+0.2% vs B&H +20.4% — latches lag vertical months.
6. Bench (near-miss): G2 volgate +2.69/t 1.71 but worst month −17.4% fails the −15% bar.
7. Rejected: pullback-in-trend (−2.60/mo, negative edge), vol-scaling without gate (tail fail), breakout hold alone (t 0.83), multi-horizon momentum (late-cycle, worst −23%), funding-gradient ("crowd building" inverts the gate's benefit).
8. Baseline recompute came out HIGHER than the brief (+2.36/+2.92 vs +1.12/+1.67) — stricter bar adopted; discrepancy flagged as harness-version drift, not reproduced.
9. Engine copy validated to 0.0 equity diff vs framework over 195k bars; all laws honored; read-only zones untouched; no live processes disturbed.
