# GATES v3 — formal spec (2026-10-09)

Supersedes v2 window rules in deployment-candidate evaluation. The generation
loop has effectively run v3 since 2026-10-06 (monthly windows on the sealed
4.5y archive); this document makes it law and extends it with JP's segment
directives (2026-10-07).

## Window structure
- OOS windows: MONTHLY (30d), walk-forward, sealed span 2021-01-01 → 2026-07-28.
- Holdout (Jul 28 → Sep 28 2026): judged on these same rules, ONE run, never
  optimized (engine-enforced since 2026-10-07).
- Medium-term view (JP 2026-10-05): candidates also report ROLLING 6-MONTH
  OOS aggregates — the minimum horizon for behavior claims.

## Per-window rules (charter v2, monthly granularity)
1. DOWN-SHIELD: bench ≤ 0 → strat ≥ 0.2 × bench
2. PARTICIPATION: 0 < bench < +15% → strat ≥ 0.6 × bench
3. EXTREME: bench ≥ +15% → strat > 0
4. Segment sub-rules (scored, reported; hard-veto only at deployment gate):
   - V-shaped windows (bench drop ≥3% then rise ≥3%): up_capture target ≥ 0.6
   - down-leg excess reported per window; crash-earning celebrated, shielded
     minimum enforced by rule 1

## Aggregate gates (deployment candidates)
- mean OOS excess ≥ +2% (monthly windows, sealed span)
- consistency t > 0
- adaptive activity: ≥ 8 entries total, ≥ 2/active window, ≥ 25% windows active
- noise stability ≥ 0.75
- time-in-market report: time_out_pct per window (out-penalty lives in the
  fitness law; gates REPORT it so cowardice is visible)
- MDD vetoes (fitness law): window > 15% or run > 25% or crash-shield breach
  → candidate purged

## Cross-asset
- ETH candidates report BTC transfer scores (same windows, BTC book);
  graceful degradation expected, collapse = warning flag.

## Scoring note
Specialist (formula-level) evaluation keeps the phase-2 doctrine: in-regime
consistency ≥ 2 independent episodes + out-of-regime flatness/earning.
The all-weather aggregate applies to ROUTER/BLENDER candidates only —
single specialists are components, not deployment candidates.
