# RESEARCH LEDGER — Crypto Alpha Program

Single source of truth for: doctrine, what was tried, what's scheduled.
Updated at every major decision. Format: date | item | verdict | lesson.
Vault (MEMORY.md/HEARTBEAT.md) carries pointers, not details.

## 1. DOCTRINE (standing decisions — JP-approved unless noted)

| date | doctrine |
|---|---|
| 10-01 | Charter v2 (asymmetric): down-shield 0.2×bench / participation 0.6× / extreme >0 / aggregates |
| 10-05 | Fitness law: return-only reward; drawdown = pure cost (MDD/5)^1.5; vetoes 15%win/25%run/crash-shield(½bench, down-leg scoped) |
| 10-07 | Segment metrics: down-leg excess + up-capture (recovery-start entry) first-class |
| 10-07 | Out-penalty: free ≤10% flat, then ((out−10)/10)^1.5 pts (JP tightened 20→10 on 10-09) |
| 10-09 | Long-only specialist weights in blends (anti-specialists banned — v1 exploit) |
| 10-11 | Seal held until bull seat filled (JP); ~2-week checkpoint ≈ Oct 25 |
| 10-13 | Detector = critical path (JP: "regime misdetected ⇒ alphas worthless") |
| 10-13 | NN placement: regime classification / skill-labels, NOT blend weights (refit-cadence law) |
| 10-13 | Skill-map labeling (JP): regimes defined by WHICH alphas work, not price-shape abstractions |
| 10-14 | NETTED fee accounting (JP): fees on change in NET exposure only — internal ledger, not per-specialist trades |
| 10-14 | **JP law v2**: MDD free ≤15%, linear multiplicative haircut to 65% (supersedes monotonic cost + 15/25 vetoes); crash-shield veto RETAINED (JP-approved 17:11) |
| 10-14 | Execution policy: maker entries (0.02%) / taker protective exits (0.05%) |
| 10-15 | Crash-shield SOFT: x=(SDD-ADD)/ADD*100 (reading C, JP-confirmed); g-rate data-anchored per-market: interp(BDD, [p25-of-market-BDDs, 50], [0.05, 1.0]) — ETH p25=8.9 |
| — | Sim fee 0.0008 = conservative floor; holdout reports taker/maker scenarios; venue = OKX perp sub-account, 1× only |

## 2. EXPERIMENT LEDGER (major arcs; formulas 001-055 detail in tuner/runs/)

| arc | verdict | lesson |
|---|---|---|
| formulas 001-010 | all REJECT | charter gates work; melt-up quadrant empty; down-profit reproducible (010 +3.1) |
| compositing 011-014 | CLOSED | 4 architectures, 0 melt-up entries — single streams can't hold both regime-blind + regime-aware; SWITCH don't blend |
| trend-riding 025-026 | harness-limited | ride-truncation was TUNER-side (take cap 8→15→30 ATR; signal_exit 0.05) |
| selection problem 027-028 | fixed by archive | ride-configs unfindable without trend-months in TRAIN → 4.5y archive (Oct 5) |
| down-leg earner 035/040 vs 041-047 | 2 hits / 6 tries | crash-profit real (+46 excess ×2); recipe fragile; routing mandatory |
| bull latch 048→050 | **CHAMPION 050** | binary pinned hold beats graded memory; up-capture 0.97 (2022-08 V) + 0.75; +7.1/mo best-ever formula mean |
| router v1→v2.2 | down-arch proven 5y | down months 4/4 profitable; grind state fixed w08; Schmitt hysteresis; bull misses persist |
| blender v1 | EXPLOIT discarded | negative weights = unimplementable anti-specialists; audited before celebrated |
| **blender v1b** | **CHAMPION family** | +4.64%/mo, t 1.81, MDD 14.7; stack ALL GREEN (jitter plateau, BTC transfer 79%, bootstrap 2.6%, PBO ≈0) |
| blender v2 (12-pool) | LOCAL OPTIMUM TRAP | 3 seeds agree: defensive trio 3.08 < v1b 5.44; TPE trapped >40 dims; fix = enqueue v1b seed |
| microstructure cache | shallow-but-accruing | OKX public depth: funding ~100d/OI 180d/taker 72d; daily top-up daemon |
| regime grid | 48 series live | detector params change regime shares 15-35% — detector choice matters |

## 3. INFRASTRUCTURE (what exists)

- 4.5y archives ETH+BTC ×15m/1h (2021→2026-09, overlap-verified) · depth recorder (Oct 5, ~25MB/mo) · macro digest daily 07:50 UTC (Oct 9) · funding/OI/taker accrual · holdout seal (library-level, engine-enforced) · precompute: 12 specialist curves + 48-detector regime grid · segment metrics · blender (v2.1 tonight: enqueue v1b + detector dim) · graph suite (v4 specs) · loop: 4 cycles/day, 5y sealed layout, leg-level feedback

## 4. SCHEDULE / OPEN ITEMS

**Near (this week):** v2.1 blender tonight (v1b-seeded + detector grid) → 4-gate stack on winner · skill maps + hand-built-detector audit (JP's labeling idea, foundation for NN) · alpha loop: bull-bench deepening (050 cross-breeding)
**Pending JP:** CoinGlass Hobbyist $29-90 (quantitative past; decision window ~2wk) · seal opening (after complete family)
**Mid (2-4 wks):** GDELT PIT news pipeline (free; days of engineering) · NN regime-classifier spec on skill labels · bull-seat checkpoint Oct 25 · quarterly blend refit doctrine formalized
**Long:** NN regime classifier trained (skill labels + macro columns + news features) · cross-sectional features (dominance/relative-strength) · BTC book · live deployment path (paper 2-4wk → sub-account 1×)

**Standing checkpoints:** Oct ~25 bull-seat/seal revisit · Gemini reviews only at contested designs (next: post-v2.1 if forks emerge)
