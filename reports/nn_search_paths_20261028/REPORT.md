# NN-ASSISTED SEARCH PATHS — DESIGN BRIEF + FALSIFICATION PILOT RESULTS (2026-10-28)

DS subagent design brief (JP directive 2026-10-28). AGENT_CONTRACT.md applies: no canonical
performance number below comes from anywhere but `tools/stats_canonical.py` via
`tools/screen_candidate.py`; AUC figures are model diagnostics, not performance claims.
The 2026-10-22 NN verdict (honest-no to NN-as-driver/router) STANDS and is treated as
immovable absent new evidence. This brief designs the three LAWFUL roles, pre-registers
kill numbers for each, and EXECUTES the cheapest one (Pilot A) under frozen spec.

**Headline: the top-ranked path is DEAD by its own pre-registered kill number, and the
non-NN control arm is 0/5 canonically. Both learned search (shallow GBM) and dumb
enumeration over threshold-conjunction rules fail to transfer on ETH 15m at this data
scale. The verdict extends the 10-22 "no" from logistic-at-2-splits to GBM-at-6-folds +
enumeration-at-2908-rules. Details in §5; raw artifacts in this directory.**

## 1. The three lawful roles — architecture + pipeline on our data

Common substrate (fixed by the contract): ETH 15m OHLCV+funding cache (~195k bars,
2021-01..2026-09; exam window read = 2021-01..2026-06, sealed holdout untouched),
fund_pct injected per `build_fund_pct('binance')`, BTC cache for conditioning. Host
reality measured: **sklearn 1.9.0 present; lightgbm, torch, gplearn ABSENT; 2 vCPU,
~5GB free RAM.** Consequence: every "NN" below is necessarily shallow ML (linear /
depth-2-3 GBM / ≤8-unit MLP) — which is also the honest ceiling at n≈63 monthly
observations of any horizon label. Nothing here justifies installing more.

### Role 1 — Miner whose OUTPUT is explicit formulas (rule extraction) — PILOTED, KILLED

- **Model class:** `HistGradientBoostingClassifier(max_depth=3, max_iter=150, lr=0.05,
  min_samples_leaf=500, l2=1.0)` — sklearn-native, ~seconds/fit on 2 cores. A shallow
  GBM IS a rule library: every root→leaf path is a conjunction of thresholded causal
  features, exactly the native language of the formula engine (cf. 10-22: the one
  signal that ever transferred was a one-threshold rule).
- **Inputs:** 12 causal features (10 screenable from OHLCV+fund_pct: returns 24h/7d,
  vol 24h, ATR%, Donchian position/distance, funding pctl, vol-ratio, tod sin/cos;
  2 diagnostic: BTC-30d momentum, ETH−BTC 30d RS). Full frozen list: PILOT_A_SPEC.md.
- **Targets:** binary label, tradeable forward return `close[t+H]/open[t+1]−1 > 0.002`
  (cost hurdle 2×8bp+ε), H ∈ {96 (1d), 672 (7d)}.
- **Splits:** expanding walk-forward F1/F2/F3 (train through 2022/2023/2024, valid
  2023 / 2024 / 2025-2026H1), NO shuffle, embargo = H bars on train tail.
- **Output path to a formula file:** surviving leaves (train leaf P(y=1) ≥ 0.55,
  support ≥ 2000 bars, screenable features only) → conjunction → literal pandas
  expression in `calculate_math_signal()` → `tuner/validate_formula.py` (with a
  `fund_pct` presence guard so the AST+causality proof passes — 076a itself fails the
  generic validator on that synth-data limitation, so the guard is a validator fix in
  the candidate, not a convention change) → `tools/screen_candidate.py`, once each.
- **Verdict: KILLED AT K1.** See §5.

### Role 2 — Feature-maker (learned representations as new declared columns) — DESIGNED, DEMOTED LAST

- **Model class:** PCA → `MLPRegressor(1 hidden layer, ≤8 units, linear output)` as a
  tiny nonlinear autoencoder over the same 12-feature block, fit walk-forward; loadings
  + activation coefficients frozen per lineage.
- **Outputs become formulas WITHOUT infra change** — this is the key design point: a
  latent defined by a frozen linear (or fixed-activation) map of rolling-causal features
  is itself expressible as a pure formula with inlined constants
  (`lat1 = Σ wᵢ·fᵢ(t)`). No injection amendment needed if loadings are frozen BEFORE
  any screen and shipped inside the formula file. Latents then enter the standard
  pipeline: threshold/conjunction rules over {lat1..lat3} → validate → screen.
- **Targets/splits:** same labels and walk-forward as Role 1; the latents must be fit
  on train folds only, applied frozen to valid.
- **Honest standing objection (why this ranks last):** a linear autoencoder IS PCA, and
  3 PCs of 12 features are strictly less expressive than the 12 features for any
  downstream shallow model. The 10-22 anti-transfer result (0.68→0.41) says the binding
  constraint is label noise / regime nonstationarity, NOT representation. Role 1's death
  (§5) is direct evidence: the raw feature block already supports train AUC 0.69-0.85 —
  memorization is easy, transfer is the problem, and no re-representation fixes that.

### Role 3 — Search guide (diversity miner over candidate space) — DESIGNED, PREMATURE

- **Model class:** any tabular learner (L1 logistic suffices) over CANDIDATE-STRUCTURAL
  features (indicator families present, window deciles, gate loci, turnover, trigger
  count, exposure profile) → P(screen-pass | structure) → reorders the loop's generation
  queue weekly. No fitting on returns at all; output = exploration priorities, never
  numbers, never formulas.
- **Why premature TODAY:** the ledger holds ≈200 screened candidates with ZERO passes
  (29 loop + 14 classics + 101 WQ + 27+27 family + 3 loop-constitution + today's 5).
  A supervised guide needs positive examples; an all-fail ledger supports only
  "explore untried families uniformly," which needs no learner.
- **Trigger to revisit:** ≥5 battery-passing candidates across ≥2 distinct families.
  Until then its honest form is a charter paragraph (diversity quota + family base
  rates), not a model.

## 2. Multiple-testing ledger for machine-generated candidates

- **Unit of account = LINEAGE, not formula.** A lineage = (generator, feature-set hash,
  label horizon, split protocol, extraction params). Every formula from one run carries
  `# LINEAGE: <id>` in its header; the coordinator appends one append-only ledger row
  per lineage (fields: id, date, generator, n_generated, n_screened, n_pass, n_battery_pass).
  Correlated formulas inside a lineage count ONCE for multiplicity — effective N = L
  (lineages), not F (formulas).
- **Generation budget:** 10 lineages/week, ≤10 formulas/lineage (loop idea-cards counted
  in the same ledger under their own generator tag).
- **H0 pass-rate prior:** 0 passes in ≈200 graded candidates program-wide → p0 ≤ 1.5%
  per candidate (rule of three). Report `E[false passes] = N_screened × p0` beside any
  pass. A pass is **believable-pending-battery** only if E[false passes] < 0.5 for the
  week's screened total (satisfied by the budget above, F ≤ 100: 100×0.015 = 1.5 → a
  pass in a max-budget week is NOT believable on its own; at typical ≤40 screens it is).
- **The extractor-contamination rule (new, standing):** a candidate whose passing window
  was SEEN by the generator (train ∪ valid) can never be seal-grade on that window.
  Confirmation requires windows untouched by any selection path (the existing seal
  logic), because the generator is just another selection layer — the same reason the
  tuner's 63-window optimum isn't quoted as OOS.

## 3. Cheap falsification pilots (kill numbers)

| path | pilot | single kill-number | status |
|---|---|---|---|
| Role 1 | Pilot A: GBM extractor, 6 fits, AUC diagnostics; then ≤10 extracted rules screened canonically | **K1:** median valid AUC < 0.53 for BOTH horizons, OR train−valid gap > 0.15 in ≥2/3 folds for both → dead. K2: 0/10 canonical passes → dead. | **EXECUTED: K1 = DEAD** (§5) |
| Role 2 | Latent pilot: PCA/MLP-autoencoder latents fit walk-forward; each latent alone → fwd-24h sign AUC | No latent reaches valid AUC ≥ 0.53 on 2024+ AND no latent adds ≥ +0.02 AUC over the raw-block logistic → dead | NOT RUN — Role 1's death + PCA⊂raw-features argument make it lower-value than its compute; would run only on new evidence |
| Role 3 | Guide pilot: leave-one-family-out P(pass\|structure) over the ≈200-candidate ledger | LOFO AUC ≤ 0.55 → dead. **Currently vacuous: 0 positives.** | PREMATURE — trigger ≥5 passes |

## 4. Ranking + the LLM/SR honesty question

**Ranking for this program: Role 1 ≻ Role 3 ≻ Role 2** (Role 1 first because its kill
number doubles as the program-level answer to "is there ANY learnable shallow structure
in 15m forward returns beyond the one-threshold BTC/funding gates" — maximal information
per CPU-hour; Role 3 is free but empty until the ledger contains passes; Role 2 cut).

**Does LLM+symbolic-regression (no NN) dominate? Mostly yes, and it was measured:**
- Role 2: dominated outright (PCA argument above).
- Role 1's GBM: a GBM is just a deterministic search over axis-aligned threshold
  conjunctions — the same space a grammar enumerator (or an LLM emitting formulas from
  the same grammar, which the loop already is post-charter) covers. **The pilot ran the
  non-NN control arm explicitly (§5): dumb enumeration's best-of-2908 died 0/5
  canonically, exactly like the GBM.** gplearn/torch are absent anyway; nothing in the
  measured evidence justifies installing them. The honest conclusion is NOT "use the
  LLM+SR variant instead" — it is that SEARCH OVER SHALLOW CONJUNCTIONS IS EXHAUSTED at
  this feature-block/target scale, regardless of who does the searching: GBM, enumerator,
  or LLM. What has never been tried is a different MECHANISM story (the only thing the
  charter lets back in), or materially different inputs (real OI/depth history, the
  accruing microstructure caches), or a different label horizon family. The one signal
  that ever survived — BTC-30d trend, a one-threshold rule — was found by mechanism
  reasoning, not by search, and search never rediscovered it (it is in the 2908, buried
  among 2907 corpses).

## 5. PILOT A RESULTS (executed under frozen spec, 2026-10-28)

Diagnostics (`diag_results.json`), runner (`pilot_a_runner.py`), spec (`PILOT_A_SPEC.md`),
candidates + verbatim screens (`candidates/`, `screen_results.json`).

**AUC table (M1 = L1 logistic, M2 = GBM; format train→valid):**

| fold (valid span) | H=96 M1 | H=96 M2 | base | H=672 M1 | H=672 M2 | base |
|---|---|---|---|---|---|---|
| F1 (2023) | 0.555→0.548 | 0.741→0.560 | 0.446 | 0.622→0.571 | 0.847→0.577 | 0.521 |
| F2 (2024) | 0.563→0.523 | 0.697→0.525 | 0.492 | 0.605→0.564 | 0.810→0.618 | 0.518 |
| F3 (2025–26H1) | 0.557→0.506 | 0.687→0.520 | 0.462 | 0.604→0.487 | 0.777→**0.477** | 0.462 |

**K1 verdict: DEAD.** H96: median valid AUC 0.525 < 0.53. H672: median 0.577 ≥ 0.53 BUT
train−valid gaps 0.270/0.192/0.300 → > 0.15 in 3/3 folds (memorization without transfer),
and the most recent-regime fold is ANTI-transfer (0.477) — the same era signature as
every 2024+ door kill. Extraction stage correctly not run (spec: only on K1 pass). K2 not reached.

**Control arm (grammar enumeration, non-NN): 2908 scorable threshold-conjunction rules**
over the 10 screenable features (F2-train quantile thresholds; selection window exactly
the 2024+ door). Best-of-2908 selection excess ≈ +0.96%/mo → the top-5 screened
canonically, once each:

| candidate | md5 | canonical mean excess | t | 2024+ excess | floors |
|---|---|---|---|---|---|
| nnC_001 | e71994fa | −0.53 %/mo | −0.20 | — | FAIL (0/4-class: mean, 2024+) |
| nnC_002 | d400a581 | −0.91 | −0.40 | −0.49 | FAIL |
| nnC_003 | 650879c8 | −0.77 | −0.30 | −0.60 | FAIL |
| nnC_004 | 2f203ff6 | −1.40 | −0.60 | −1.10 | FAIL (halves too) |
| nnC_005 | 526c56aa | −1.87 | −0.89 | −1.18 | FAIL (halves too) |

0/5. The winner's-curse collapse (selection +0.9 → canonical −0.5..−1.9 on the very
selection window's era) is the pilot's second lesson: **in-window selection maxima are
advertising, not evidence** — the canonical screen did its job at O(1) cost per candidate.

Multiple-testing note: this entire pilot = ONE lineage (`NNPILOT-A-20261028`), 5
screened, 0 passes; E[false passes] at p0≤1.5% ≈ 0.08 — no believable-pass question arises.

**Candidate formula files** (self-contained, `fund_pct`-guarded, all carry the lineage
header): `candidates/nnC_001..005.py`. Screening staging copies under
`models/alpha_formulas/` were md5-recorded and removed; nothing outside `reports/` committed.

## 6. Infra asks (declarative only; NONE block anything that survived — nothing survived)

1. **None required for the state of evidence.** The killed paths needed zero new columns
   or runners, by design: rule outputs are plain formula files; latent outputs are
   inlinable frozen linear maps; the guide's output is a ranked list for the existing
   charter cron.
2. **IF** a future extractor ever passes K1 with >50% of surviving leaves on BTC
   conditioning (measured trigger in the runner; today's run never reached extraction):
   amendment INJ-btc — extend `tools/screen_candidate.py` to inject `btc_mom` (30d BTC
   momentum, reindex-ffill, same convention as fund_pct). Operator-approved tool change;
   not requested today.
3. **Amendment NN-1 (ledger hygiene, cheap, recommended):** require `# LINEAGE:` header
   + one ledger row per machine-generation run (the §2 scheme). Charter-level, JP call.
4. Validator nit, no action forced: generic `validate_formula.py` synth data lacks
   `fund_pct`, so ANY gate-in-formula candidate fails it (076a included, verified today).
   Either add the guarded-injection convention to the validator's synth frame or accept
   the candidate-side guard pattern used here. Cosmetic; the causality proof is the part
   that matters and it is unaffected.

## 7. Bottom line

The 10-22 verdict is reaffirmed with six more folds, two horizons, and a measured control
arm: at ETH-15m scale with this feature block and these labels, learned search (GBM) and
dumb enumeration both die at their pre-registered numbers, and nothing about "NN"
justifies more infrastructure. The program's scarce resource is MECHANISM stories and
NEW INPUTS (the accruing OI/depth caches are the only genuinely new information on
disk), not smarter search over the same 12 features. Recommended spend after this pilot:
zero further compute on Roles 1-2 until either (a) new inputs exist, or (b) ≥5
battery-passing candidates make Role 3's guide non-vacuous.
