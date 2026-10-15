# BLENDER FITNESS LAW v1 — 2026-10-07 (JP-approved)

The Saturday blend optimizer's fitness function. Every term traces to a JP
directive; nothing here is tunable *by* the optimizer (a tunable risk
appetite is meta-overfitting). Calibration constants are locked BEFORE the
sweep starts and recorded in the run config.

## Positive reward — RETURN ONLY (JP 2026-10-05)
- `excess`: OOS mean excess vs B&H per walk-forward window — the ONLY
  source of positive feedback. As much as possible.
- `consistency`: direction agreement across windows (t-stat sign) — secondary.

## Segment terms (JP 2026-10-07)
- `down_excess`: strategy minus bench return over the window's down-leg
  (bench trough split). Rewards shielding AND short-earning.
- `up_capture`: strategy up-leg return / bench up-leg return (V-windows).
  Rewards RECOVERY-START ENTRY: full capture requires being in from the
  leg's beginning. Target ≥ 0.6 in V-shaped windows.

## Drawdown — JP LAW v2 (2026-10-14; supersedes 10-05 monotonic cost + 15/25 vetoes)
- Free zone: MDD <= 15% -> no penalty.
- Linear score haircut: 15% < MDD < 65% -> final = raw_score x (1 - (MDD-15)/50).
- MDD >= 65% -> score zeroed. Multiplicative: returns buy drawdown tolerance
  proportionally (JP example: raw 100 @15% beats raw 150 @40% -> 75).

## Time-out penalty (JP 2026-10-07) — "out is legal but expensive"
- `time_out_pct` measured from equity curves (in-position bars = MTM
  movement; flat bars = no movement).
- `penalty_out = ((time_out_pct − 10) / 10)^1.5` excess points, zero below
  10% (JP 2026-10-09: band tightened from 20): 20% out → 1.0 pt · 30% → 2.8
  · 40% → 5.2 · 60% → 11.2.
- Doctrine: default posture is LONG (crypto drift). Short requires
  confirmation; OUT requires confirmation. The router's states already
  comply (grind_down cash is 48-bar-confirmed; expansion defaults long).
  Cowardice must be out-earned, and the shield free-rider problem dies.

## Crash-shield — SOFT (JP 2026-10-15; replaces the last hard veto)
- Allowance: SDD <= frac(BDD) x BDD, frac linear 0.7 at BDD<=10% -> 0.5 at BDD>=50%.
- Excess x (percentage points) penalizes the score percentage at rate linear
  from x/10 (BDD<=10%) to x (BDD>=50%), summed over crash windows, capped 100.
- Multiplicative with the law-v2 MDD haircut: final = raw x (1-mdd_frac) x (1-shield_pen%).
- x defined as percentage POINTS of excess drawdown (JP confirmed reading pending).

## Total
    score = w_e·excess + w_c·consistency + w_d·down_excess + w_u·up_capture
            − penalty_mdd − penalty_out            (vetoed candidates: −inf)
    w_e=1.0, w_c=0.3, w_d=0.3, w_u=0.3 (defaults; final values recorded
    in run config before the sweep)

## Protocol guards
- Nested walk-forward on 2021-01-01 → 2026-07-28 (sealed); holdout
  Jul 28 → Sep 28 consumed ONCE, after, by the final verification run.
- PBO (CSCV) computed on the sweep; reported with the result.
- WINDOW-BLOCK BOOTSTRAP (r50 Q3, adopted-modified): winner's stored
  per-window results resampled at monthly granularity (episode-preserving;
  path-shuffling variants REJECTED — they destroy regime episodes, the
  structure our edge lives in). Report excess distribution + stability;
  zero extra simulations. Path-shuffle archives: not adopted.
- Hysteresis: chop<->expansion boundary uses a Schmitt trigger (enter
  <0.75, exit >0.85). Weight-fading at transitions: REJECTED (re-imports
  blend dilution, alphas 011-014; the fast lane stays fast).
- Free flat-time band: 10% (operator decision 2026-10-09, tightened from 20).
- Specialist pool admission: quadrant-segment quality per phase-2 doctrine
  (in-regime consistency ≥ 2 episodes; out-of-regime flatness/earning).
