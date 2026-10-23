# alpha_076c — MACHINE A × BTC-30D-TREND ENTRY GATE ("A+gate" product candidate).
# Pre-registered pilot spec (FROZEN 2026-10-22, before running):
# reports/router_nn_ideas_20261022/REPORT.md §3. Pilot build only — launches
# nothing; JP's nod gates any promotion.
#
# Base = alpha_076a (Machine A: raw turtle192 latch, funding gate INSIDE the
# formula). ONE delta on top of A: entries additionally require the BTC 30d
# momentum state to be UP (ETH breakout latches continue only when the
# complex's trend state is up; in BTC downtrends, ETH breakouts are bull
# traps). Blocked breakouts produce NO entry event (a missed breakout is NOT
# remembered — re-arm needs a fresh breakout); rides CONTINUE to A's own
# structural exits: neither the BTC gate nor the funding gate ever blocks an
# exit (structural exits rule the latch; entry-gating is the mechanism that
# survived — multiplicative gating falsified, RESEARCH_LEDGER 2026-10-22).
# Warmup CLOSED: NaN btc_mom => comparison False => gate closed (same NaN
# convention as the fund_pct gate). Causality: the gate state is shifted 1
# bar (frozen spec: "state shifted 1 bar"); the engine additionally fills at
# the next bar.
#
# Contract: the engine injects the causal BTC momentum ratio series as a
# 'btc_mom' column into this frame (WQAlphaParams.use_btc_mom_gate; same
# seam/pattern as the 'fund_pct' column injection, funding_gate_mode='formula').
# Series built by the pilot harness as btc_close / btc_close.shift(96*30) on
# the OKX BTC 15m close, reindex-ffill to the ETH exec index (frozen pilot
# notes: 15m BTC data, 96*30-bar shift).
#
# Config (selection-free law): 30d window / 1.00 threshold = plateau centroid
# of the 16-cell surface (window {14,30,60,90}d x thr {0.98,1.00,1.02,1.05},
# all 16 cells positive, btc_stress.py). 14d/0.98 (grid max) is NAMED AND
# FORBIDDEN as the reported config. One ratio, one threshold, chosen because
# it is the centroid — nothing fitted, no search.
#
# Funding COST is never charged here (evaluation overlays, JP laws); funding
# gate block frozen identical to alpha_076a (binance, pctl 0.7, formula mode).
# Provenance: REPORT §2c (the one router-program survivor) + pilot launch
# approval 2026-10-23. KILL criterion: anchored exam <= A's or jitter sign
# flip -> gate dies, static A stays the product.
import numpy as np
import pandas as pd

# Frozen exam defaults — identical to alpha_076a (only the BTC gate differs).
PARAMS = dict(
    long_threshold=0.5,
    short_threshold=0.55,          # long-only formula; exam runs allow_shorts=False
    signal_smoothing=1,            # binary latch — smoothing MUST stay off
    atr_period=14,                 # engine-side disaster-rail ATR only
    atr_stop_mult=50.0,
    atr_take_mult=50.0,
    max_position_pct=1.0,
    warmup_candles=100,
    use_bias_filter=False,
    signal_exit_threshold=0.5,     # structural release => sig=-1 <= -0.5 => exit
)
# Machine A funding gate (unchanged from alpha_076a): gate lives INSIDE the
# formula via the injected 'fund_pct' column; the engine-level gate stays OFF.
FUNDING_GATE = dict(
    use_funding_gate=True,
    funding_gate_pctl=0.7,
    funding_input="binance",
    funding_gate_mode="formula",
)
# BTC-trend gate (THE 076c delta): engine must inject the ratio series as a
# 'btc_mom' column when params declare use_btc_mom_gate=True. The window is
# applied where the series is BUILT (96*30 on the 15m grid); the threshold
# lives here, frozen at the plateau centroid.
BTC_GATE = dict(
    use_btc_mom_gate=True,
    btc_mom_window_bars=96 * 30,   # 30d of 15m bars (series built by the caller)
)
BTC_MOM_THRESHOLD = 1.00          # plateau centroid (NOT the 14d/0.98 grid max)


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low = df["close"], df["high"], df["low"]
    fund = df["fund_pct"]    # injected by the engine (funding_gate_mode='formula')
    mom = df["btc_mom"]      # injected by the engine (use_btc_mom_gate)
    th = high.rolling(192, min_periods=96).max().shift(1)
    tl = low.rolling(192, min_periods=96).min().shift(1)
    prev = close.shift(1)
    tr = pd.concat([high - low, (high - prev).abs(), (low - prev).abs()],
                   axis=1).max(axis=1)
    atr = tr.rolling(96, min_periods=32).mean()
    # Gates INSIDE the state machine (entry events only; exits never gated):
    #   funding (Machine A): only an UNCROWDED breakout raises an entry event.
    #   BTC trend: only a trend-UP breakout raises an entry event, state
    #   shifted 1 bar (frozen spec causality).
    # NaN in either series => comparison False => gate closed (warmup closed).
    uncrowded = (fund < 0.7).fillna(False)
    btc_up = (mom > BTC_MOM_THRESHOLD).shift(1).fillna(False)
    above = (close > th) & uncrowded & btc_up
    below = close < tl - 1.0 * atr
    # Event markers -> state machine: ev[exit]=0, ev[entry]=1 (entry
    # precedence), forward-fill, 0 before the first event. No expanding().max()
    # — every release re-arms the entry; missed (gated) breakouts are NOT
    # remembered: re-arm needs a fresh breakout. Identical to alpha_076a.
    ev = pd.Series(np.nan, index=close.index)
    ev[below] = 0.0
    ev[above] = 1.0
    latch = ev.ffill().fillna(0.0)
    return (latch * 2.0 - 1.0).clip(-1.0, 1.0).fillna(-1.0)
