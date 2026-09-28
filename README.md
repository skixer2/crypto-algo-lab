---
type: project-note
project: crypto_trading_bots
tags: [crypto_trading_bots]
created: 2026-09-14
updated: 2026-09-28
---

# Crypto Trading Bots

Live bots + framework. This directory IS the git repo (private:
`github.com/skixer2/crypto-algo-lab`) — versioning insurance after the
2026-09-14 source-loss incident.

## Bots
1. **OKX RSI Scalper Pro v3.1** — `live_rsi_scalper_okx.py` (source in repo)
   ETH/USDT:USDT futures, 15m, RSI14 [30/70], SL 2% / TP 3%, 20% equity, 3x,
   bidirectional. Equity = OKX totalEq; sizing in contracts (v3.1, 2026-09-20).
2. **Revolut RSI v2** — bytecode only (`live_trading_revolut_v2.pyc`, source
   lost). Runtime home (OUTSIDE the repo, security purge 2026-09-28):
   `../crypto.pre_dedup_20260918/pyc_archive/` (pyc + config.py + state dir).
   BTC/EUR spot, 1m, RSI14 [30/60], 25% equity, limit orders, EMA50>EMA200
   buy filter. Needs Python 3.11 exactly.

## Layout
- `framework/` — the 12-module trading framework (ported scraping_rules)
- `models/` — the swappable model slot (new algorithms go here)
- `lib/` — okx_candle_fetcher, revolut_client_new.py (client source)
- `docs/` — charter + FRAMEWORK_BRIEF.md (AI briefing)
- `config.py` — loads `.env` + `.env.root`. DO NOT COMMIT creds (gitignored).
- `logs/` — live bot logs (gitignored)
- Startup: `./start_trading_bots.sh` (idempotent; hourly watchdog cron)

## Security
- No compiled bytecode, no credentials, no state files in git (purged from
  history 2026-09-28 with git-filter-repo; `*.pyc` gitignored).
- Brain card (vault): `1_Projects/crypto_trading_bots.md`.

## TODO
- Decompile the Revolut pyc back to source (needs a 3.11-capable decompiler);
  once done, the source replaces the bytecode in pyc_archive and can live in
  the repo.
