"""
alpha_039 — CONFIRMED-BREAKDOWN REGIME + RECLAIM OSCILLATOR (P1 earner, hybrid)
Hypothesis (post-mortem of alpha_038): a constant deep-negative short signal
NEVER crosses the tuner's trade thresholds (0 entries in the test month,
2/2.0 activity, noise stability null) — the exact structural failure that
killed 011/012/013. The fix is alpha_014's anatomy (entries by construction:
a mean-zero fast oscillator swept across thresholds by a slow regime mean)
with an UPGRADED regime clock and a reclaim latch on the long side:
  regime = tanh(1.2*reg_z):
    - NEGATIVE only on 2-day CONFIRMED breakdown (close sustained below the
      4-day Donchian mid, alpha_038's confirmation logic) — shorts harvest
      the down leg with tanh(depth*20) amplitude (down-leg RETURN > 0 goal),
    - POSITIVE on structural reclaim: cross back above the mid with volume
      confirmation, latched by an ewm that decays slowly (recovery-start
      buyer, P2-lite) so V-window entries are not shaken out by pullbacks.
  osc = tanh(-1.5*z_fast): zero-mean 16-bar return-z mean-reversion,
  guaranteeing threshold re-crossings in chop AND inside trends (bounce
  scalps in bears, dip buys in bulls).
  Composite: 0.55*regime + 0.45*osc. Both bounded; divisions guarded;
  trailing ops only (rolling/ewm); imports numpy/pandas only.
Bear-rally trap (2022-01 +14.4 inside bear): the short only engages while
the 2-day confirmation holds; a genuine reclaim (volume-backed closes above
mid) flips the regime within ~half a day.
Charter rules attacked: adaptive_activity (oscillator re-crossings),
down_shield WITH PROFIT (confirmed shorts), uptrend_participation +
extreme_participation (regime positive + dip buys at reclaim), P1
down-leg earner, P2 recovery-start lite.
Author: auto-gen (isolated alpha loop), 2026-10-09.
Provenance: tuner/runs/alpha_038_auto.json (0 entries — threshold failure),
alpha_014 (entries-by-construction anatomy), alpha_038 (confirmation +
amplitude logic), alpha_010 (reclaim unlock w/ volume surge).
Inputs: OHLCV.
"""
import numpy as np
import pandas as pd


def calculate_math_signal(df: pd.DataFrame) -> pd.Series:
    close, high, low, volume = df["close"], df["high"], df["low"], df["volume"]
    eps = 1e-9

    # ---------- structure: 4-day Donchian mid (trailing) ------------------
    w_mid = 96 * 4
    hh = high.rolling(w_mid, min_periods=w_mid // 2).max()
    ll = low.rolling(w_mid, min_periods=w_mid // 2).min()
    mid = ((hh + ll) / 2.0).ffill()

    dist = ((close - mid) / mid.replace(0, eps)).clip(-0.15, 0.15).fillna(0.0)

    # ---------- regime: confirmed breakdown vs volume-backed reclaim -------
    is_below = (dist < 0).astype(float)
    conf_2d = (is_below.rolling(96, min_periods=48).mean()
               .rolling(96 * 2, min_periods=96).mean().fillna(0))
    confirmed = (conf_2d >= 0.9).astype(float)

    depth = np.tanh(dist * 20.0)  # -1..1, negative below structure

    v_rel = (volume / volume.rolling(96 * 7, min_periods=96 * 2)
             .mean().replace(0, eps)).clip(0, 2).fillna(1.0)
    vol_ok = np.tanh((v_rel - 1.0) * 0.5)  # -1..1

    reclaim = ((dist > 0.002) & (vol_ok > -0.2)).astype(float)
    # latch: slow ewm of reclaim keeps regime positive through pullbacks
    reclaim_latch = reclaim.ewm(span=96 * 2, min_periods=48).mean().fillna(0)

    # down-speed amplitude (48h return z, clipped)
    r48 = close.pct_change(96 * 2).fillna(0).clip(-0.5, 0.5)
    r48_mu = r48.rolling(w_mid, min_periods=w_mid // 2).mean()
    r48_sd = r48.rolling(w_mid, min_periods=w_mid // 2).std().replace(0, eps)
    speed_z = ((r48 - r48_mu) / r48_sd).clip(-2, 2).fillna(0)

    short_regime = confirmed * depth * (1.0 + 0.5 * np.tanh(np.maximum(speed_z, 0)))
    long_regime = np.tanh(1.5 * reclaim_latch) * (1.0 + 0.3 * np.tanh(vol_ok))
    regime = (short_regime + long_regime).clip(-2.0, 2.0)

    reg_mu = regime.rolling(96 * 4, min_periods=96 * 2).mean()
    reg_sd = regime.rolling(96 * 4, min_periods=96 * 2).std().replace(0, eps)
    reg_z = ((regime - reg_mu) / reg_sd).clip(-2, 2).fillna(0)
    reg_term = np.tanh(1.2 * reg_z)

    # ---------- fast zero-mean oscillator (entries by construction) --------
    ret = close.pct_change()
    vol = ret.rolling(48, min_periods=20).std().replace(0, eps)
    z_fast = (ret.rolling(16, min_periods=8).sum() / (vol * np.sqrt(16.0))
              ).replace([np.inf, -np.inf], 0).clip(-2, 2).fillna(0)
    osc = np.tanh(-1.5 * z_fast)

    sig = 0.55 * reg_term + 0.45 * osc
    return sig.clip(-1.5, 1.5).fillna(0.0)
