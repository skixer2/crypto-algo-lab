# Bull Champion + Mining + Blender — Strategy Advisory (DeepSeek V4 Pro subagent, 2026-10-18)

Method: read ledger + review + honest-search artifact, then **7 cheap experiments run today on the
bench** (all scripts in `/tmp/bull_exp/exp{1..7}.py`, evidence CSVs in `reports/bull_evidence_20261018/`).
Repo untouched. ETH 15m OKX archive, seal 2026-07-28; honest pairing = shift-1 throughout; netted
fee 0.0008/unit exposure change; t-stats over 64 monthly windows (2021-04..2026-07) unless noted.
Numbers below are physically plausible and reproducible from the scripts.

---

## 1. BULL CHAMPION PLAN

### 1.0 The one-line problem, quantified

Every honest long-side number in this program dies the same death: **down-month excess positive
(+3 to +16), up-month excess negative (−2 to −20)**. The bench did +2.14%/mo mean over the 64
windows (30/64 up). A long/flat seat with up-capture c and down-protection p has expected excess
≈ p·E[exc|dn] − (1−c)·E[up|up]. The pool's best bull performer today (alpha_050, the turtle latch)
does exactly this: +0.28 mean excess, −7.43 up-month / +7.08 down-month (honest shift-1, embedded
fees — `pool_profile.csv`). **The bull seat is not missing; it is structurally defensive at this
frequency. The question is how much offense honest entries can carry.**

### 1.1 Recruitment evidence — what actually carries forward return on the long side

**(a) The detector's expansion lane is information-free for offense.** Lane-conditional forward
returns (detector 25 = honest-search winner, seal span, `lane_conditional_fwd.csv`):

| lane | share | fwd edge over uncond @1 bar | @16 bars (4h) | @96 bars (1d) | @672 (1w) |
|---|---|---|---|---|---|
| expansion | 55.6% | **+0.000%/bar** | +0.0001% | +0.034% | +0.148% |
| confirmed_bearish | 28.2% | +0.0006 | +0.0066 | **−0.034** | **−0.151** |
| vol_compressed | 13.3% | −0.0008 | −0.0178 | −0.097 | −0.523 |
| grind_down | 2.9% | −0.0002 | +0.0162 | +0.115 | +1.019 |

The expansion label ≈ unconditional at tradable horizons; the **bear label is the only lane with a
stable conditional tilt (negative)**. Flip bars confirm: entering long on a flip→expansion bar
earns −0.042% fwd-16h vs +0.021% unconditional (n=2377). **The detector is a bear detector. Route
defense with it; never source offense from the expansion lane.** (This also kills the naive
"hold long in expansion" strategy: −6.5%/mo excess, t −4.09, both detectors.)

**(b) Breakout structure is the only real long-side primitive found.** Turtle latch (enter close >
trailing N-high, exit close < N-low − 1·ATR), 189 honest round trips 2021-2026:
win rate **35.4%**, mean outcome **+1.77%/entry**, median **−1.78%** — a fat-right-tail payoff.
Positive mean in every year (2021 +5.1, 2022 +0.2, 2023 +0.9, 2024 +2.9, 2025 +1.3, 2026 −0.9).
Up-leg anatomy (`upleg_anatomy.csv`, 50 legs ≥15%): honest entry lags the trough by median 33h and
captures **median 0.76 / mean 0.67 of each leg gross** — the capture exists; the bleed is the 65%
of entries that fail. Exit design matters more than entry: a 3-ATR chandelier trail churns 22
trades/mo and destroyed the tail (−2.79 mean excess); a 2-ATR trail degenerates entirely (exits
inside the noise band, never re-enters — seat sits flat, excess = −bench). Keep the wide structural
latch.

**(c) Positioning (funding) is the missing conditioning variable — the session's main find.**
Turtle entry outcomes split by funding-rate percentile (30d rolling, Binance ETH proxy, causal):

| bucket at entry | n | fwd-1d mean | hit rate |
|---|---|---|---|
| funding pctl < 30 | 620 | **+0.294%** | 50.2% |
| mid | 846 | **+0.340%** | 53.0% |
| funding pctl > 70 (crowded) | 882 | **−0.259%** | 42.7% |

Crowded breakouts fail; uncrowded ones continue. Gating entries at pctl<0.7:

| variant | mean excess | t | MDD | exc_dn | exc_up | trades/mo |
|---|---|---|---|---|---|---|
| turtle192 ungated | +1.12 | 0.77 | 53.5 | +7.96 | −6.63 | 5.6 |
| **turtle192 + gate<0.7** | **+2.21** | **1.58** | 47.1 | +9.14 | −5.65 | 4.9 |
| gate<0.5 | +1.98 | 1.16 | 43.7 | +10.21 | −7.33 | 4.3 |
| gate<0.3 | +2.11 | 1.10 | 41.9 | +11.32 | −8.32 | 3.0 |
| gate<0.7, shift-2 | +2.32 | 1.64 | 50.3 | — | — | — |

Robustness: gate plateau (all gates ≥ ungated), relabel-invariant (shift-2 retains 105%),
**walk-forward improves** (train 21-23 +1.45/t0.67 → test 24-26 **+3.01/t1.70**), yearly 4/6
positive (2022 +50, 2024 +63, 2025 +37, 2026 +40; loses 2021 −242 vs mania bench — the gate blocks
mania entries that worked there — and 2023 −41). **This is the first honest candidate with t>1.5.**
Still not significant; funding cost not yet charged (see 1.3); treat as lead, not champion.

**(d) Dead ends measured today (so nobody re-mines them):** EMA cross 15m/1h (−1.1/+1.1, t<0.7);
donch 96/288 (−0.97); pullback-in-trend RSI variant (−2.3, 0.1 trades/mo at sane frequency);
vol-target alone (−3.3); daily SMA200 (t 0.14) and daily donch 20/55 (t 0.09) — frequency is not
the binding constraint, fees are 0.03-0.6%/mo across variants; the information source is.
**BTC→ETH lead-lag at 15m is dead in naive form**: ETH fwd-16h after BTC-up vs BTC-down windows =
+0.005% vs +0.044% at k=1 (REVERSED); tradable version t −5.7. Detector entry-veto (block breakouts
in confirmed_bear) HURTS (−1.04): the structural stop fires long before the 48-bar bear confirmation,
and the veto blocks good bottom breakouts. Use the detector for exits/damping, never as entry gate.

### 1.2 Fitness law for SELECTION (avoiding the flip-rent trap in the bull seat)

The trap is **worse in the bull seat than it was in the blend**: breakout bars return **+0.865% mean
vs +0.0014% unconditional** (n=1728), so any same-bar-close evaluation of a breakout formula books
+5.1 to +11.1%/mo of rent — 3-18× the honest edge. The gated turtle at n_hold=96 scores **+11.72
(t=7.05!) under shift-0** vs **+0.62 (t=0.43) honest** — a fake champion of review-killing strength
in one parameter. Note: **WARN-5 same-bar-close fills mean the stored alpha_048→050 curves embed a
slice of exactly this rent; expect their honest re-sims to drop.** Selection law (all mandatory):

1. **Shift-1 pairing is the floor, and shift-0/shift-1 rent must be reported**: alarm if rent > 25%
   of shift-0 edge (existing guard) — plus the new, stronger bull-seat guard: **absolute honest edge
   must be ≥ +1%/mo for rent to be meaningful at all** (below that, any rent share is noise).
2. **Relabel-invariance shift-2 ≥ 0.75 retention** of shift-1 (passed today: 105%).
3. **Plateau, not peak**: candidate must be positive (≥ +1%/mo honest) across the declared grid
   (n_hold {96,192,288} × gate {0.5,0.7,0.9}); reject grid-max selection — today's data shows 96
   collapses (+0.62) while 192/288 hold (+2.21/+1.59): select the plateau centroid, not the max.
4. **Walk-forward mandatory**: rolling train-24mo/test-3mo, report test-window excess only; plus the
   hard 21-23→24-26 split must be positive. Full-span selection = the proven overfit (WARN-2).
5. **Charge funding at the seat layer**: long time-in × realized funding rate (proxy until OKX deep
   history exists). Measured: long 1.0× pays **11.5%/yr equity on average (37.5% in 2021!)** — that
   is ~0.55%/mo at the gated turtle's 57% time-in, cutting +2.21 to ≈ **+1.65 net**. The bench is
   price-only; an uncharged funding number is dishonest by construction (INFO-8 of the review).
6. **Per-unit-exposure metrics for seats** (not standalone MDD — the blend owns MDD): mean excess
   netted, up-month excess, failed-break bleed (median entry outcome), trades/mo ≤ 6, out-time ≤ 60%.
   Do NOT let the MDD law select the seat (it would just re-create the defensive pool); apply JP's
   MDD law at the blend layer.

### 1.3 Validation gates before pool entry

1. Honest re-sim on the NEW engine (fee-free curve + next-open fill + intrabar SL/TP + CRITICAL-2
   bias fix). Next-open vs next-close is small in 24/7 crypto (mean |gap| 0.004%, p99 0.036%) but
   same-bar-close → next-open is exactly the rent channel for breakouts: expect honest numbers to
   fall; the candidate must survive the fall.
2. Guards: flip-rent monitor + relabel-invariance + plateau (1.2) + walk-forward (1.2-4).
3. Funding overlay charged; report with AND without (both in the artifact, per venue-fee doctrine).
4. Stress slices: 2022-05, 2022-11 (intrabar stops now real), 2021-01 (worst full-span DD episode),
   2026-07 (the unreported −21% honest month), FTX week.
5. Cross-asset transplant on SOL/BTC with identity stated (weights+detector+fee model) — exploratory
   only, quarantined from selection until ETH-only verdict exists.

### 1.4 Is the bull seat fillable at 15m? Ceiling estimate

**Yes — but only as a fat-tail harvester with a positioning gate, not as a smooth earner.**
- Evidence-supported ceiling: **+1.5 to +2.5%/mo mean excess net of netted fees, before funding;
  ≈ +1 to +2 net of funding** (t ≈ 1.2-1.7 over 64 windows). That is the gated breakout latch today;
  a well-mined grid over the family (entry structure × positioning conditioning × sizing) might
  reach +3%/mo honest at best — I would not plan on more.
- Structural negatives that no 15m topology fixes: up-month excess stays −5 to −8 (honest entries
  lag by construction — the flip-rent analysis PROVED the fast money is unbookable); MDD per seat
  40-55% standalone; 2021-mania capture is inversely related to the gate that saves 2022-26.
- **Horizon**: 1h and 1d decision variants did NOT beat 15m (similar or worse mean excess at
  near-identical fee drag) — moving the decision timeframe does not import information that isn't
  there. The lever is the conditioning variable (positioning/funding), not the bar size. Keep 15m
  execution; add funding + later OI/liquidation data as inputs (CoinGlass decision now justified —
  the funding gate alone was the single largest honest improvement found today).
- Expected seat contribution inside the blend: replaces alpha_050's slot at roughly 4× the honest
  mean excess (+2.2 vs +0.28) with the same defensive shape — it raises the floor and modestly the
  ceiling; it does NOT make the pool offensive. **Plan the pool's offense around multiple
  regime-conditional seats, not one bull champion.**

---

## 2. BEST-ALPHA MINING STRATEGY (stop manufacturing survivors)

**Substrate first, then mine.** The imminent rebuild (fee-free curves, next-open fills, intrabar
stops, CRITICAL-2 bias fix) changes every curve's value — for breakout families by potentially
half. **Re-mine from scratch on the honest engine; salvage only the data pipeline, the detector
grid, and the failure ledger.** Do not salvage curve-based weights: they were selected under a
different physics (WARN-3's double-fee incoherence is retired by the same act).

1. **Formula-space by measured priors.** Fund families in order of today's evidence: (i) breakout
   latch × funding gate (the +2.21 lead), (ii) structural latch variants (ATR-buffer widths,
   N asymmetric enter/exit), (iii) pullback-in-trend at LOWER frequency (daily filter, weekly-scale
   entries — today's version died on frequency; the family isn't falsified), (iv) positioning
   overlays on any of the above. Deprioritize: EMA crosses, RSI means, BTC-lead, lane-conditional
   longs (all measured dead today or in the ledger).
2. **Parameterization discipline**: small declared grids (≤ 3 dims), report the whole grid surface,
   select plateau centroids; ban TPE over 40+ dims on the reporting windows (the v2 trap is
   documented — TPE found the rent). Every candidate ships with its grid table, not just its point.
3. **Nested walk-forward as the ONLY selection objective**: train window → pick → score untouched
   test window; the reported number is the concatenation of test windows. Full-span stats are
   diagnostics, never selection targets. PBO/CSCV on monthly blocks as a second gate; block-3
   bootstrap CI reported on the walk-forward stream.
4. **Honesty guards in the objective** (already law, extend): shift-1 pairing, rent share monitor,
   relabel-invariance, coverage asserts (zero-exposure impossible), fee = netted law, funding charged.
5. **Every candidate carries a kill-document**: what mechanism it exploits, why it can't be lookahead
   (which bar closes when), and the exact forward-return conditioning measured on unselected data.
   Candidates without a mechanism story don't enter the pool even if they pass the gates — that is
   the structural fix for survivorship bias (the pool is a museum of mechanisms, not of P&L).
6. **Failure ledger parity**: every mined family gets its dead-end entry with numbers (like 1.1d
   today) so the next mining wave starts from evidence, not hope.

---

## 3. BEST BLENDER — verdict and build order

**Verdict: lane-routing is the right frame for DEFENSE and the wrong frame for OFFENSE — because
it was never offense-capable.** The lane labels carry a real conditional tilt only on the bear side
(−3 to −15 bps/day in confirmed_bearish; expansion ≈ unconditional). The honest search's shape
(seg_dn +15.3 real, up-capture −0.15) is not a search failure; it is the objective finding the only
signal the labels contain. Alternatives, concretely:

- **Continuous blend (no lanes)**: rejects. Any continuous weighting of the same detector inherits
  the same (bear-only) information; slower weights just smear the flip-rent into basis-point dust.
  Nothing to blend on the long side but noise.
- **Per-specialist online gating (skill-based on/off)**: right idea, wrong time. With 13 curves of
  which several never trade and the pool lacking honest offense, gating selects defense again.
  Revisit as blender v3 AFTER the pool has ≥ 3 honest seats with distinct mechanisms.
- **Vol-target overlay at the blend layer**: yes — adopt. Cheap, orthogonal, and it satisfies JP's
  MDD law mechanically instead of through selection pressure (which is what bred the all-defensive
  pool). Measured at seat level: 0.9-target kept excess (+2.09) while capping MDD; at blend level it
  converts the seat's standalone 47% MDD into a portfolio-legal exposure.
- **JP doctrine (NN predicts oracle skill labels causally → route)**: correct as the END STATE, and
  today's evidence sharpens it: the oracle labels worth predicting are "which seats earn next," and
  the detector's bear-tilt is the trivial first feature. But an NN trained on the current pool learns
  to predict defense. Build it after the honest offensive pool exists (see order below).

**Recommended build order with this codebase:**

1. **Rebuild wave** (already decreed; now with a measured stakes-estimate: breakout-family curves
   can lose 30-60% of claimed edge under next-open fills — the +0.865% breakout-bar rent).
2. **Bull-seat recruitment sprint** (1-2 weeks): formalize the gated latch family per §1.2-1.3;
   grid {192,288}×{0.5,0.7}; walk-forward selection; funding overlay; ship alpha_070+ as
   fee-free curves. Target: one seat with honest walk-forward excess ≥ +1.5%/mo net.
3. **Blend v3-honest**: lanes for defense (bear/grind/chop) + seat weights in expansion chosen by
   walk-forward, NOT by TPE on the reporting windows; funding gate as a portfolio-level input;
   vol-target overlay enforcing the MDD law; netted fees; flip-rent + relabel guards run on every
   trial (they're cheap and would have saved Saturday).
4. **Deepen the offensive pool**: pullback-in-trend (daily), positioning overlays, cross-sectional
   only if BTC-ETH lead-lag is re-tested with proper microstructure lag (today's naive test says no).
5. **Then** online per-specialist gating (v3) and the NN skill-label classifier — the pool is
   finally worth labeling.

---

## EXECUTIVE SUMMARY

1. Expansion lane has ZERO forward-return edge (0.0 bps/bar @1-16 bars); bear lane has real
   negative tilt. **The detector is a bear detector: route defense with it, never source offense.**
2. Honest breakout latch = only real long-side primitive: 35% win, +1.77%/entry, fat right tail;
   median entry −1.78%. Wide structural stops beat chandelier trails (tail preservation).
3. **MAIN FIND: funding-gated breakouts.** Crowded breakouts (funding pctl>70) have −0.26%
   fwd-1d; uncrowded +0.29/+0.34%. Gate at pctl<0.7: **+2.21%/mo honest excess, t=1.58**,
   plateau across gates, shift-2 invariant, OOS improves (+1.45→+3.01). First honest t>1.5 lead.
4. Bull-seat ceiling at 15m: **+1 to +2.5%/mo net** (funding −0.55%/mo at 57% time-in; longs paid
   11.5%/yr average, 37.5% in 2021). Up-month excess stays −5 to −8: the seat is defensive
   participation with carry, not offense. 1h/1d variants don't beat 15m — conditioning, not bar
   size, is the lever.
5. **The rent trap is 3-18× bigger in the bull seat**: breakout bars return +0.87% vs +0.001%;
   same-bar evaluation shows t=7 fake champions. Stored alpha_050 lineage numbers are suspect
   under same-bar-close fills (WARN-5). Guards: shift-1 floor + rent-share monitor + shift-2
   retention ≥0.75 + grid plateau (reject n_hold=96-class spikes) + funding charged.
6. Re-mine from scratch on the honest engine; salvage pipeline + detector grid + failure ledger
   only. Small declared grids, plateau centroids, nested walk-forward as sole selection objective,
   mechanism story required for pool entry, dead-ends recorded with numbers.
7. Blender verdict: lane-routing correct for defense, structurally incapable of offense; continuous
   blend rejected; online gating premature; **adopt blend-level vol-target overlay** to satisfy the
   MDD law mechanically instead of via selection pressure. NN skill-labels = end state, after the
   honest offensive pool exists.
8. Build order: rebuild wave → gated-latch bull seat (alpha_070) → blend v3-honest (walk-forward
   weights, funding gate, vol-target) → deepen offensive pool → gating/NN.
9. CoinGlass decision is now evidence-backed: funding conditioning was today's largest single
   honest improvement; OI/liquidation data is the same lever with more resolution.
