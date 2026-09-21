---
type: project-note
project: crypto_trading_bots
tags: [crypto_trading_bots]
created: 2026-09-14
---

# Crypto Trading Bots

Live bots (recovered 2026-09-14 after accidental source deletion; JP confirmed cause).

## Bots
1. **OKX RSI Scalper Pro v3** — `live_rsi_scalper_okx.py`
   ETH/USDT:USDT futures, 15m, RSI14 [30/70], SL 2% / TP 3%, 20% equity, 3x, bidirectional.
   REWRITTEN from log-evidenced v2 spec (source was lost, no .pyc existed).
   Syncs existing exchange position on boot.
2. **Revolut RSI v2** — `live_trading_revolut_v2.pyc` (+ `revolut_client_new.pyc`)
   BTC/EUR spot, 1m, RSI14 [30/60], 25% equity, long-only. RECOVERED as Python 3.11 bytecode
   (runs directly with `python3 file.pyc`; source lost). Requires python 3.11 exactly.

## Files
- `config.py` — Config class; loads `.env` + `.env.root` (REVOLUT/OKX keys). DO NOT COMMIT.
- `.env.root` — OKX + Revolut private creds, chmod 600.
- `logs/` — live bot logs.
- Startup: `./start_trading_bots.sh` (idempotent watchdog, run hourly by cron).
- Brain card (vault): `1_Projects/crypto_trading_bots.md`. Research trees: `../trading-bots/`.
- Pre-relocation archive: `../crypto.pre_dedup_20260918/`.

## Versions
- OKX bot **v3.1** (2026-09-20, JP-approved): equity = OKX totalEq (v3.0 read cash USDT only,
  under-reported ~50%); sizing in CONTRACTS via contractSize=0.1 ETH (v3.0 lot-clamped trades
  to ~4-8% of intended size). Backup: `live_rsi_scalper_okx.py.v3.bak-20260920`.
- Revolut v2: unchanged (bytecode, source lost).

## PIDs
- `/tmp/live_rsi_scalper_okx.log.pid`, `/tmp/live_trading_revolut_v2.log.pid`

## TODO
- Decompile revolut pyc back to source when a 3.11-capable decompiler is available.
- Consider source control (private repo) so this never happens again.
