# Deployment roadmap — where new strategies will trade

JP (2026-09-30): "use the two wallets of Revolut and OKX where the actual
strategies are already running, without big success." — Agreed. Those wallets
are the live testbed. No new venues, no new capital until live proof.

## Phase 1 — OKX first (the proving ground)

The first formula that passes the Charter gates deploys on the **OKX wallet**
(~$107 totalEq), replacing the incumbent RSI Scalper Pro v3.1.

Why OKX first:
- **Infrastructure is proven end-to-end**: ccxt works, the v3.1 bot's position
  sync / sizing / watchdog / pidfiles are battle-tested; the framework's
  `LiveExecutor` builds on the same ccxt stack.
- **Futures allow shorts** — full Charter compliance (down-shield can use
  shorts, not just cash).
- **Fee model matches the backtests** (0.08%/side assumption ≈ OKX taker).
- Path: PROMOTE → paper mode (engine sim on live data) 1–2 weeks → live small
  (existing balance, existing sizing discipline) → incumbent retired.

## Phase 2 — Revolut (the second front)

A **long-only Charter variant** deploys on the Revolut wallet (~€70),
replacing Revolut RSI v2. The Charter is achievable long-only: down-shield
via cash (≥ 0 means flat is legal), participation via longs.

Preconditions (engineering, not research):
- Wire `lib/revolut_client_new.py` into the execution path (the framework's
  `ccxt.revolut` branch is dead code — documented).
- **Fee-model correction**: re-run the champion's backtests with Revolut X's
  actual fee schedule before deployment; the 0.08% assumption is OKX-derived.

## Sizing & succession

- Existing balances ARE the test sizing. Scaling up = JP's decision, only
  after live confirmation across regimes (weeks, not days).
- Incumbents keep running until their replacement passes; the Charter's
  `edge_vs_champion` gate treats the live bots' performance as the baseline
  to beat.
- One champion per wallet at a time (champion/challenger lineage in
  `tuner/runs/`). Portfolio aggregation of multiple winners = Phase 3, only
  after a second champion exists — via a composite Model (engine unchanged).

## Automation boundary

Generated formulas NEVER touch execution: signals only, the engine owns
orders (contract-enforced). The generation cron cannot trade, cannot read
credentials, writes formulas only.
