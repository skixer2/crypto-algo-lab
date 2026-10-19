# Engineering note: funding-gate plumbing (2026-10-19, in progress)

Goal: formulas may declare a funding gate so candidates like alpha_076 (and DS
round-2 recruits with gates) run through the standard engine instead of ad-hoc
bar arithmetic. All numbers previously verified ad hoc must reproduce.

## Parameters (WQAlphaParams extension)
- `use_funding_gate: bool = False`
- `funding_gate_pctl: float = 0.5`   # enter only if funding rank < this
- `funding_input: str = "avg"`       # binance | bybit | avg (both CSVs in data_cache, full span, free/public live)

## Semantics (must match the verified scripts exactly)
- Visible at bar t: only SETTLED funding (00/08/16 UTC) with settle_ts <= bar
  close time (ts + exec_delta). reindex(..., method="ffill") of the settled
  series onto the exec index implements this (settlements are stamped AT
  settle time).
- Gate series = 30-day rolling percentile rank of the settled rate series
  (96*30 bars, min_periods 96*7), ffilled to 15m bars — identical to the
  verified latch scripts (rolling on the 15m-ffilled rate, NOT on the 3/day
  native series; keep the same convention or the ranks shift).
- Funding input "avg" = elementwise mean of the two venues' ffilled rate
  series BEFORE the rolling rank.
- Entry gating only; exits never gated (structural exits rule the latch).

## Seams
1. FastContext gains optional `fund_pct: Optional[pd.Series]` aligned to
   exec_df.index (orchestrator builds it when params.use_funding_gate).
2. Fast model (`wq_alpha_fast.FastWQAlphaMinerModel`): at anchor init, slice
   fund_pct from `self._base` like run_df; `predict()`: entry actions AND-gated
   by `fund_pct.iat[tick-1] < pctl` (mirror of the existing bias_bull gate —
   same pattern, second condition).
3. Direct model (`wq_alpha_miner.WQAlphaMinerModel`): needs the series passed
   in (it has no context); orchestrator attaches `model.fund_pct = series` and
   predict() consumes it if present. Both paths MUST produce identical gates
   (equivalence test below enforces).
4. Funding COST is NOT charged here: standalone cost overlays and blend-level
   netted+funding stay in evaluation (existing methodology, JP laws).

## alpha_076 formula (raw turtle192 latch — DS design, loop-corroborated)
- Lesson from the loop's alpha_070.py: `latch = gate.expanding().max()` pins
  FOREVER after the first breakout (release only via the struct_ok factor) —
  that is why its up-capture was 0 after early saturation and the loop
  rejected it. 076 must be a proper re-armable state machine:
  entry: close > rolling(192).max(high).shift(1)
  exit:  close < rolling(192).min(low).shift(1) - 1.0*ATR96
  Vectorize causally: build entry/exit event markers, forward-fill state
  (0 -> 1 at entry, 1 -> 0 at exit), no expanding().max().
- Signal mapping into the formula interface: sig = latch state (0/1); entry
  threshold low (e.g. long_threshold 0.5); manage exit via signal flip
  (signal_exit_threshold small) OR structural exit in-formula (state machine
  already encodes it — sig 0 forces exit). Engine stops remain as disaster
  rails only.
- Params frozen per exam: N=192, exit channel N=192, ATR mult 1.0, ATR period
  96, gate pctl from plateau {0.5,0.7} on averaged input (both variants
  through the exam; OOS decides — JP 2026-10-19).

## Tests (gate: do not merge without all passing)
1. Gate series spot-check: fund_pct at 5 known timestamps == ad-hoc script
   values (±1e-9).
2. Gated vs ungated runs differ ONLY at bars where an entry was blocked.
3. Fast-vs-direct equivalence (6-month slice, gated formula): max rel div
   < 1.0e-9 (they share only OHLCV+funding — must be bit-identical).
4. 076 raw latch via engine vs my verified bar-arithmetic position series:
   positions agree >= 99% of bars (order-path differences allowed at fills).

Status: design filed 2026-10-19 ~10:05 UTC; implementation next session-block.
