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

## Drawdown — PURE COST, no zero-reward floor (JP 2026-10-05)
- `penalty_mdd = (MDD% / 5)^1.5` in excess points: each 5% of drawdown
  costs at least one point, superlinearly beyond.
- 5% MDD → 1.0 pt · 10% → 2.8 · 14% → 4.7. Return leads; turbulence must
  be out-earned.
- Final k calibrated ONCE from pool MDD/excess distribution before the
  sweep, then locked and documented.

## Time-out penalty (JP 2026-10-07) — "out is legal but expensive"
- `time_out_pct` measured from equity curves (in-position bars = MTM
  movement; flat bars = no movement).
- `penalty_out = ((time_out_pct − 20) / 10)^1.5` excess points, zero below
  20%: 30% out → 1.0 pt · 40% → 2.8 · 60% → 6.5.
- Doctrine: default posture is LONG (crypto drift). Short requires
  confirmation; OUT requires confirmation. The router's states already
  comply (grind_down cash is 48-bar-confirmed; expansion defaults long).
  Cowardice must be out-earned, and the shield free-rider problem dies.

## Veto lines — kill-switches, NEVER targets (JP 2026-10-05)
- per-window MDD > 15% → candidate purged (score = −inf)
- full-run MDD > 25% → purged
- crash-shield: when bench draws down > 20% in a window, strat MDD must be
  ≤ ~half the bench's, else purged ("−25% tolerable only if market −50%":
  tolerated, never rewarded)

## Total
    score = w_e·excess + w_c·consistency + w_d·down_excess + w_u·up_capture
            − penalty_mdd − penalty_out            (vetoed candidates: −inf)
    w_e=1.0, w_c=0.3, w_d=0.3, w_u=0.3 (defaults; final values recorded
    in run config before the sweep)

## Protocol guards
- Nested walk-forward on 2021-01-01 → 2026-07-28 (sealed); holdout
  Jul 28 → Sep 28 consumed ONCE, after, by the final verification run.
- PBO (CSCV) computed on the sweep; reported with the result.
- Specialist pool admission: quadrant-segment quality per phase-2 doctrine
  (in-regime consistency ≥ 2 episodes; out-of-regime flatness/earning).
