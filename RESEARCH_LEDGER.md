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

### 2026-10-16 — fast-vs-direct CLOSED; transfer comparison error attributed (v21e≠v21g)
- Per-specialist ranking: fast=direct 0.0% for 15/18 curves; SOL 032 17.8% (2021-02-18), SOL 056 2.8%, BTC 056 1.5% (head-edge). Portfolio artifacts: tuner/runs/chaos_ranking.json, tuner/runs/v21g_fast_vs_direct_portfolio.json.
- The "+13.7/+2.5 vs +20.6/+9.4" gap was NOT fast-vs-direct: fast transfers ran v2.1e+det12 (artifact Oct 15 06:33, subtitle self-identifies "v2.1e on BTC... detector-12... +2.45%"); direct rebuild = v2.1g+det7 (born 07:03). Two different champions compared as one. Transfer-gate "inconclusive" verdict RETRACTED — v2.1g cross-asset: SOL +20.60, BTC +9.37 (construction-verified).
- Standalone 035 on SOL: equity → 0.0x (short-squeeze chain-stop); routed portfolio unaffected — router is load-bearing on foreign assets.
- RULE (named, 5th instance of comparing-different-things): STATE THE CANDIDATE'S IDENTITY (weights file + detector + fee model) BEFORE comparing any two numbers.

### 2026-10-16 (PM) — CORRECTION: transplant numbers were fee-free; honest netted numbers shipped
- Root cause found (my bug, not the auditor's): direct compose string-mapped {"long","short"} onto NUMERIC position columns in auditor CSVs -> all positions 0 -> zero netted fees. Yesterday's "+20.6 SOL / +9.4 BTC" were FEE-FREE. Morning "v21e-vs-v21g identity" attribution also incomplete: the dominant term was the missing fee, not version identity.
- Canonical verify: my compose reproduces official ETH v2.1g via stored curves under the netted law (gate tol 0.15). Stored weights are 3dp-rounded (vol_compressed sums 1.001 -> evaluate() -inf on re-run; gate uses compose arithmetic).
- HONEST v2.1g cross-asset (netted, both paths agree): see tuner/runs/v21g_transplant_CORRECTED.json; graphs v21g_{SOL,BTC}_direct.html regenerated with fee-drag + turnover in subtitle.
- Rule: assert position parse coverage >0 before composing (zero-exposure portfolio impossible); compose via canonical evaluate() formula only.

### 2026-10-16 (PM) — LIVE RISK RAILS v0 — **PROVISIONAL: TO BE CONFIRMED ON THE FIELD** (JP, 15:02 UTC)
- Design (JP-approved direction, soft-law mirrored in live): de-risk rail 20% continuous DD (halve exposure, alert) · kill-switch 25% (flatten + review; restart = JP decision only) · slow-bleed alarm on rolling-quarter excess vs bench (threshold = worst backtest rolling quarter; exact value to be computed in execution spec). Measured on LIVE account equity incl. fees+funding actually paid.
- Basis: continuous DD distribution 2021-2026 (132 episodes >=3%: median 4.6%, p90 11%, max 19.5%; top-4 cluster 18.7-19.5%, recoveries 1-33 d). CRITICAL: the 15.0% champion stat is the WINDOWED (calendar-month) fitness metric — live rails must NEVER anchor on it (15x1.2=18% would have whipsawed 4x in production).
- **STATUS: FIELD-UNVERIFIED — hypothesis from backtest distribution only.** Paper-live pilot must confirm: no-whipsaw on real books, trigger mechanics, slow-bleed calibration. Promotion to standing doctrine only after pilot review. OWNER: JP confirm; ZioClaw instrument.

### 2026-10-16 18:19 UTC — SEAL SEQUENCE DECIDED (JP): seal AFTER the independent review
- v2.1g seal waits for the DeepSeek V4 Pro adversarial review (subagent ds-v4pro-audit, running) — and implicitly the last 5 knob-jitter readouts. Any CRITICAL finding from either blocks the seal until resolved; clean review -> seal executes without further debate.

### 2026-10-16 19:0x UTC — 🚨 CRITICAL: BLEND-LAYER LOOKAHOOK — SEAL BLOCKED — blend program quarantined
- DS V4 Pro review (reports/deepseek_v4pro_review_20261016.md) found, and I INDEPENDENTLY VERIFIED (tuner/runs/lookahead_verify_v21g.json): blender.py evaluate() pairs lane[t] (computed from close[t]) with ret[t] (move ending at close[t]) = one-bar lookahead.
- My reproduction, ETH v2.1g, same weights/curves/months: AS-SHIPPED +7.33%/mo (t +2.96, FTX +22.2) -> HONEST pairing wl[t-1]*ret[t]: **-5.29%/mo (t -2.46, FTX +2.6), negative 4/6 years**. Flip-bar rent: +12.5 pts/mo = 170% of the shipped edge, from 3.75% of bars. (Reviewer's secondary conditional P=0.77 not reproduced by my conditioning — non-load-bearing; the pairing-shift test is decisive and agrees exactly.)
- CONTAMINATED (quarantined, do not quote): every blend-level number from this evaluate() — v2.1g ETH/SOL/BTC + transplants + funding-at-portfolio overlays, v1b champion (+4.64), all Optuna blend searches. STANDS: data pipeline (reviewer: clean, 0 dup stamps, seal held), specialist engine sims (except CRITICAL-2 pending), engine-level honesty stack, today's fee-bug correction methodology.
- CRITICAL-2 (pending my verification): simulation.py:162 feeds 1h open-stamped bias bars up to 60 min early (alpha_056/032/004, use_bias_filter).
- WARNs: rails DD distribution missing worst episode (full-span max 20.46% Jan-2021 vs 19.5 documented); t=2.96 = best-of-5000x48 in-sample; July 2026 in-seal unreported month: excess -9.4 in +18% bull month; alpha_028 never trades yet w=0.18.
- P0 (endorsed): (1) shift blend pairing one bar, regenerate everything; (2) re-run blender search under honest objective (vectorized, cheap); (3) fix 1h early feed + re-sim 3 specialists; (4) PERMANENT GUARDS: flip-bar-rent <25% monitor + one-bar relabel-invariance test in evaluate(); (5) commit ephemeral overlay/compose scripts.
- JP rule honored: CRITICAL blocks seal. Seal OFF until honest-pairing champion exists (if one does).

### 2026-10-17 09:06 UTC — STANDING LAW (JP): THE REAL-ACCOUNT FEE MODEL = netted-only
- JP's confirmed execution model, verbatim example: Alpha1 buys 100 (→pos 150), AlphaB sells 50 (→pos 100); crossing portions net internally; exchange sees ONE order +50; fee = |50| x rate. General law: fee = |desired net - current net| x rate = |Delta(Sigma w_i pos_i)| x 0.0008, per bar.
- DECREE (JP, permanent goal "the code that approaches the real result the most"): specialist curves must be FEE-FREE; the ONLY fee is the netted layer. Layer A (per-specialist embedded fees) = internal ledger fiction, never charged twice again.
- Rebuild wave (after in-flight honest search delivers): fee=0 re-sims + next-open fills + intrabar SL/TP (WARN-5, same wave, one re-simulation) -> honest search re-run under real-account model -> walk-forward gates.
- JP's paradox resolved + recorded: netting never increases a GIVEN trade's cost (B<=A per event), but B's event set includes lane-boundary weight swaps (A models none); as-built churn ~60 net-units/mo was lookahead-selected pathology.

### 2026-10-18 — DS V4 Pro strategy report (bull seat + mining + blender) — INDEPENDENTLY VERIFIED
- Report: reports/deepseek_bull_and_blender_strategy_20261018.md + evidence CSVs (bull_evidence_20261018/). My replication: gate split (+0.294/mid +0.340/crowded -0.259 fwd1d) and headline (+2.21%/mo t 1.58, halves +1.80 -> +2.62) reproduce EXACTLY.
- FIND 1: expansion lane fwd-return edge ~0 -> detector is a BEAR detector; route defense with it, never source offense. Bull seat ceiling 15m: +1..2.5%/mo (funding drag on longs 11.5%/yr avg); seat = defensive participation + carry, not offense. 1h/1d no better (conditioning, not bar size, is the lever).
- FIND 2 (the lead): funding-gated turtle192 latch (gate: 30d funding pctl < 0.7, causal): +2.21%/mo honest excess, t 1.58, plateau across gates 0.5-0.8, shift-2 invariant, OOS improves. FIRST honest t>1.5 candidate. NOT seal-grade (t bar was >=2); it is a lead, not a champion. Alpha_070 candidate. Caveat: fpct warmup uses bfill (minor, early-span only).
- FIND 3: rent trap 3-18x bigger on long side; alpha_050 stored numbers suspect under same-bar fills.
- Mining: re-mine from scratch on honest engine (salvage pipeline/detector grid/failure ledger only); declared small grids, plateau centroids, nested walk-forward as sole selection objective, mechanism story mandatory.
- Blender verdict: lane-routing = defense-only frame; continuous blend rejected; online gating premature; ADOPT blend-level volatility-target overlay to enforce MDD law mechanically.
- BUILD ORDER (endorsed): rebuild wave (fee-free + next-open fills + two-level stops per JP doctrine 09:36) -> alpha_070 gated latch -> blend v3-honest (walk-forward weights + funding gate + vol-target) -> deepen offensive pool -> online gating / NN skill-labels last.
- CoinGlass decision now evidence-backed: funding conditioning was the largest single honest improvement found to date.

### 2026-10-18 20:15 UTC — CoinGlass DECISION CLOSED (JP): no tier fits; overlap measurement replaces it
- Pricing page (JP read): funding-history depth 180d (Hobbyist/Startup) / 360d (Standard) / 720d (Professional) — cannot reach 2021 at any price. NO SUBSCRIPTION. Pending item from 2026-10-13 closed.
- Overlap measurement (native OKX recorder vs Binance proxy, 126 settlements 2026-07-14..09-30): corr 0.497 (quiet-funding window, noise-dominated near zero), sign agreement 81.7%, mean |diff| 0.00288%/8h.
- Consequences: (a) historical COST overlays carry ~±0.26 pts/mo proxy error on 1x — bounded, acceptable; (b) GATE conditioning (30d pctl < 0.7) agrees only 69.8% at settlement level — registered as a model-risk item on the latch (076) entry exam: mitigate via gate-plateau robustness (holds 0.5-0.8) + entry-moment relevance + re-validation as native OKX history accumulates (recorder running; 12mo -> full native re-validation possible).

### 2026-10-19 10:40 UTC — DS round-2 QUARANTINED: t>2 claim is a reporting-pipeline artifact
- Claim: G3_cbgate WF-OOS +2.98%/mo t 2.05 "first t>2 candidate"; incumbent recomputed +2.92.
- MY verification (3 independent routes): (1) my reimplementation of G3 center/modal per their frozen params: +0.61/+0.52%/mo, t 0.27; (2) THEIR OWN stored equity curve (curve_cg_n144_g0.5_s0.005.pkl) graded by the standard 63-window law: +0.77%/mo t 0.33 worst month -51.1%; (3) their incumbent curve: -1.04%/mo t -0.40. Curves agree with my arithmetic (~zero edge); claimed stats are ~3-4x inflated vs their own artifacts.
- Root cause (suspected, unproven): stats-layer unit/convention bug (bench_monthly.json holds FRACTIONS; excess likely mixed %-and-fraction) — the same pipeline that produced the "baseline drift" they flagged as "not reproduced" and proceeded anyway.
- G3 fails the exam on honest numbers (worst window -51 vs -15 bar). ALL round-2 graded verdicts (acceptances AND rejections) share the broken stats layer -> quarantined. Salvageable: engine-copy approach, curve artifacts, family ideas (ungraded).
- LESSONS (permanent): (a) "discrepancy flagged but not reproduced" = STOP and isolate, never proceed with the stricter bar; (b) agents never grade their own homework — stats ONLY via a canonical verified library, anchored against known-good numbers (raw latch = +1.12); (c) independent reproduction before quoting: third save (audit guard, alpha_070 gate, now round-2 stats).
- ACTION: build tools/stats_canonical.py (one grading implementation, unit-tested against anchors); loop + future DS runs MUST consume it.

### 2026-10-19 15:15 UTC — ROUND 3 (solid bases): first honest bull-seat RECRUIT CANDIDATE; one bar needs JP recalibration
- Discipline held: anchor reproduced bit-for-bit through DS pipeline (old convention +1.1190/t0.7713 EXACT); canonical ruler only; engine imported not copied; reality ratios 1.0 (gated, framework.runner) and 0.839 (ungated, fast path) — both >= 0.8 law. MY verification of their stored curve through stats_canonical: +2.11%/mo t 1.41 EXACT (worst exc -32.7, worst abs -18.8, DD -47.5, conc 0.21, halves +2.14/+2.09). Round 2's failure mode does not recur.
- CANDIDATE: turtle192 latch x binance-funding-pctl gate <0.7, NET of fees+funding, honest engine. 9/10 exam bars: mean/t/halves/conc/count/jitter(27/27)/retention(1.04)/ruin(-18.8 >= -40)/reality — all pass.
- THE FAIL: worst in-lane month -32.7 (2021-10: bench +42%, gate correctly refused crowded mania) vs the -15 bar. Calibration discovery: the -15 bar ALSO fails the known-good anchor (-27.6) — old convention ran worst-months ~2x milder; bar calibrated on the old ruler. JP DECISION PENDING: recalibrate (proposed -35) vs waiver vs reject-all.
- Per-input law paid off: bin +2.11 >> avg +1.46 >> byb +0.79 — funding-input quality is a real design variable (ledger line). Binance input free/public forever (JP cross-data doctrine).
- Rejections (honest ruler): confirmed-breakout m2/m3 negative (m1 > m2 > m3!), vol-scaled sizing dilutes the paying tail, washout-restart mechanism dead.
- Structural finding: detector-7 expansion lane = plurality in 64/64 months -> lane-conditional exam degenerates to full grid for bull specialists; bear-est-8 stress slice used as compensation (+7.83/t1.53 for the candidate). TODO: better bull-lane definition before blend v3j.
- Anchor convention note: ruler's strict month-boundary alignment vs round-1 one-bar misalignment = +0.13 drift; all r3+ numbers same-ruler (internally consistent); pre-r3 quotes carry +/-0.15.

### 2026-10-19 19:38 UTC — STANDING CONSTITUTION APPROVED (JP): Entry Exam Law v3.2 (anchored) + Blender Law

## LAW 1 — ENTRY EXAM v3.2(anchored), for candidate specialists
Principle: floors protect deployability; prices express desirability. Earn in your lane, survive out of it.
HARD FLOORS (binary): (1) OOS mean excess > 0; (2) worst ABSOLUTE month >= -40% (ruin; interlocks with engine 2x intrabar cat-stop); (3) jitter +/-15%/param, 2 draws: sign never flips, OOS stays >0; (4) shift-2 retention >= 0.25; (5) flip-rent < 25% of edge; (6) reality ratio >= 0.8 (engine vs arithmetic); (7) gate causality: settlement visible only from first decision >= 1 bar after publication.
SOFT SCORE (per-month, averaged): allowance_i = theta x BMU_i (theta calibrated BY INVERSION vs the anchor so anchor scores modest-positive ~+0.3/mo; absolute floor = pair's bench monthly return vol sigma_M). Within allowance 1:1; beyond: 2x slope; deep zone (pair-anchored ~-35 ETH): 3x; single worst month charged as if at the deep bound (one priced freak). Score = mean(s_i) over >= 8 in-lane OOS months; t on s_i; halves/concentration/July-26 disclosed as diagnostics.
PROCEDURE: nested walk-forward only (selection != reporting); stats_canonical ONLY (agents never grade their own homework); anchor-check-first + stop-on-discrepancy; anchor must score modest-positive under every parameter set; lane assignment via dominant-lane map (detector panel: det-7 = bear routing; bull-lane detector pending); blend-level exam stays standalone.
REFERENCES: 076 gated latch: raw +2.11 t1.41 -> v3.2 +1.69 t_s 1.02, ALL floors pass, provisionally admitted. Anchor raw-latch net: +0.62 -> +0.12 (fixed-knee -15; triggers theta calibration at encode). Funding inputs: binance committed (+2.11) >> avg (+1.46) >> bybit (+0.79).

## LAW 2 — BLENDER LAW (portfolio assembly & selection)
Principle: the netted book is the product; selection pressure shapes it.
MECHANICS: honest pairing shift=1 (label t acts on t+1 returns); netted-only fees 0.0008 x |Delta(sum w_i pos_i)| (curves fee-free); lane exposure cap sum|w|<=1; 63-window grid, July-26 disclosed ungraded; position-coverage assert at choke point.
REWARDS: mean excess (primary); t; seg_dn (defense); up-capture (bull KPI); parsimony.
SOFT PENALTIES (never vetoes): crash-shield per-window (ADD = frac x BDD, frac 0.7@BDD<=10 -> 0.5@BDD>=50; overshoot x=(SDD-ADD)/ADD x100 reading C; penalty = x*g) with g data-anchored (0.05@BDD=ga -> 1.0@BDD=50, ga = p25 of pair's window BDDs, ETH 8.9); MDD law v2 (free <= 15%, linear multiplicative haircut to 65%); OUT-PENALTY (prose, JP-approved wording): idleness = share of bars with net exposure under 5% of capital; free up to 10% of bars, escalating score penalty beyond — the anti-hiding clause (a blend that never trades cannot lose, cannot earn, and must not win).
SEARCH: Optuna TPE, seed-deterministic; dims = lane weights x detector grid; prior champions enqueued; walk-forward selection only (v3h/v3i were the last full-span breeds); one ruler for reporting; detector-per-lane as searchable dim (pending); vol-target overlay planned (mechanical MDD enforcement); weights stored 3dp -> _renorm on reload.
WINNER GUARDS (auto): flip-rent > 25% alarm; relabel retention < 0.25 alarm (positive edges only); July-26 always disclosed.
REFERENCES: v2.1g anti-reference (+7.33 fake -> -5.29 honest); v3i real-account baseline (best -1.21, seg_dn +14.7, MDD 10.1) = the bar v3j must beat. Netted example (JP verbatim): Alpha1 buys 100, AlphaB sells 50 -> one +50 order, fee on 50.

DEPLOYMENT LAYER (distinct): live rails v0 PROVISIONAL field-unverified (de-risk 20 / kill 25 continuous DD + slow-bleed), re-derived on first honest champion.
