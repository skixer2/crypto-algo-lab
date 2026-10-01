# Contingency: Volatility-Adjusted Trailing Brake (PARKED until trigger fires)

Trigger: 3 more generation cycles under wide-stop freedom ([1-8]) without
progress on the +3.89% chop wall. NOT before. (Set 2026-10-01, after
structural fix v1 landed in 4470bbb.)

Origin: Gemini round-9 spec — direction ACCEPTED, code REJECTED after audit.
Its realization that the trailing brake fits the EXISTING manage_position()
hook (wrapper-level change, NO engine fork) is the genuinely valuable insight.
Its implementation had three defects and one false claim:

1. STALE ATR: it read `self._last_indicators.get("atr")` — but _last_indicators
   is populated by predict(), which fires ONLY WHEN FLAT. During a held trade
   the ATR is frozen at entry-time. Its docstring ("real-time trailing
   distance using the precomputed ATR vector") describes what the code does
   not do.
2. PEAK NEVER RESETS: `if self._entry_price is None` initializes once per
   process lifetime — every trade after the first inherits the previous
   trade's peak. Fatally wrong for direction changes.
3. HARDCODED 1.5x TRAIL: the wall is tight-stop whipsaw; hardcoding another
   fixed tight multiplier repeats the original mistake. Must be a tunable
   Optuna param.
4. "bit-identical fast-path equivalence" is the wrong claim: the change alters
   behavior BY DESIGN. What must be equivalence-TESTED is fast-vs-reference
   agreement on the trailing logic itself (extend verify_fast_equivalence
   with a trailing-enabled param set; assert identical trades incl.
   trailing_hit exits).

## Corrected specification (implement at trigger time)

WQAlphaParams += `trailing_stop_mult: Optional[float] = None`  (None = off;
Optuna space: {None, 1.5, 2.5, 4.0})

Wrapper (BOTH paths, wq_alpha_miner.py + wq_alpha_fast.py):
- State: `_trail_peak: Optional[float] = None`, `_trail_position: Optional[str] = None`
- manage_position():
  - trailing off -> return None (current behavior, equivalence preserved)
  - if self._trail_position != position:  # new trade detected
        self._trail_peak = price; self._trail_position = position
  - long:  peak = max(peak, price);  exit if price <= peak - mult * CURRENT_atr
  - short: peak = min(peak, price);  exit if price >= peak + mult * CURRENT_atr
  - return "trailing_hit"
- CURRENT ATR: reference path recomputes from buffer (reuse _compute_atr);
  fast path uses self._atr.iat[self._tick - 1]. NEVER _last_indicators.
- Reset happens on position change (handles reversal + flat periods).

Ordering (already correct in the engine): physical SL/TP checks run BEFORE
manage_position — trailing complements, never overrides, the hard stop.

Validation at implementation:
1. verify_fast_equivalence extended: trailing-enabled param set, 6/6 identical.
2. Proof tests: peak resets across consecutive trades; trailing fires at the
   right bar (synthetic ramp-then-drop); trailing off = byte-identical to
   current behavior.
3. Charter gates unchanged — trailing exits are just exits.
