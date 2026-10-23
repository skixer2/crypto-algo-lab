# The Alpha Lifecycle — from candidate to deployable strategy

*Standing process documentation (2026-10-23, JP-requested). The laws referenced live in
RESEARCH_LEDGER.md (2026-10-19 constitution) and tools/stats_canonical.py.*

```mermaid
flowchart TD
    C["CANDIDATE ALPHA<br/>source: auto-loop / DS / human / JEV-shadow rule"] --> D["DECLARATION<br/>formula + frozen params + mechanism story<br/>(grid declared BEFORE touching data)"]
    D --> E["HONEST ENGINE RUN<br/>decide@close, fill@next-open, 2x intrabar rails<br/>netted-only fees, funding paid"]
    E --> R["CANONICAL RULER<br/>stats_canonical only — agents never grade"]
    R --> F{"HARD FLOORS (binary)<br/>OOS sign > 0 · worst absolute month ≥ −40%<br/>jitter ±15% sign-stable · shift-2 retention ≥ 0.25<br/>flip-rent < 25% · reality ratio ≥ 0.8 · gate causality"}
    F -- "any fail" --> L["FAILURE LEDGER<br/>never retested without a NEW mechanism story"]
    F -- "all pass" --> X{"ENTRY EXAM v3.2<br/>per-month soft scores, anchored allowance θ×BMU<br/>2x slope beyond, 3x deep, one priced freak"}
    X -- "score < anchor reference line" --> L
    X -- "score ≥ admission" --> A[("ACCEPTED ALPHA<br/>SUCCESS REGISTRY = pool manifest<br/>each entry is the alpha's certificate:<br/>frozen params · grades · provenance · chain")]
    A --> S["STATIC BOOK<br/>simplex allocation over standalone-positive recruits<br/>NO routing — frozen 2026-10-20 after three lawful kills"]
    S --> B{"BOOK EXAM<br/>same floors + soft scores at book level"}
    B -- fail --> L
    B -- pass --> W["WALK-FORWARD CONFIRMATION<br/>frozen configuration, unseen windows,<br/>stitched deployable equity"]
    W -- fail --> L
    W -- pass --> H["HOLDOUT READOUT<br/>the sealed months — the one test nobody trained on"]
    H -- fail --> L
    H -- "holds" --> P["APPROVED DEPLOYABLE STRATEGY<br/>PRODUCTION REGISTRY entry: approved config,<br/>rails, deployment state, holdout readout"]
    P --> Z["DEPLOYMENT PREP<br/>rails re-derived on real numbers (field-unverified tag)<br/>paper pilot at 1x · fills-vs-model logging"]
    Z --> LIVE["LIVE<br/>+ shadow monitors: JEV · depth · funding recorder"]
    JEV["JEV shadow log (live-only)<br/>LLM backtests are hindsight-contaminated"] -.->|"graded vs always-on + dumb gates<br/>before ANY advisory role"| LIVE
```

## Stage notes

- **Declaration before data** kills the silent overfit; the failure ledger makes rejections
  permanent knowledge unless a genuinely new mechanism justifies a retest.
- **The anchor** (raw latch, net) runs through every exam as the reference line: any bar the
  anchor cannot pass is wrong by definition.
- **Gate variants** (funding gate, BTC-momentum gate — e.g. alpha_076c) enter as ordinary
  candidates whose parent is the anchor; the exam decides whether conditioning adds or subtracts.
- **Routing is closed** at pool-size 1: with multiple standalone-positive recruits the static
  simplex reopens automatically; adaptive routing stays buried absent new evidence.
- **Holdout discipline**: the sealed months are read once, on the frozen configuration. They are
  the transition from "accepted" to "approved."
- **Where successes live**: the **pool manifest** (`data/precompute/manifest.json`) is the
  machine-readable success registry — every accepted alpha's entry is its certificate (frozen
  params, canonical grades, provenance, supersession chain — see alpha_076a replacing 076).
  **Approved deployables** get a production-registry entry (approved configuration, rails,
  holdout readout). The narrative ledger records both, but the manifests are the durable
  certificates. Failures need their dedicated ledger because they otherwise evaporate;
  successes persist structurally — in the manifest, the code, and the deployed config.
