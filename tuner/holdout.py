"""Holdout seal — deployment-candidate studies may not read past SEAL_DATE.

SEAL_DATE = 2026-07-28 (UTC). The final 2 months (Jul 28 – Sep 28 2026) are
untouched by ALL optimization; they are consumed exactly once by the final
holdout verification run before any deployment decision.

Bypass discipline (better than an env var — auditable on disk):
  1. `touch tuner/.holdout_final_run`  (creation logged in memory notes)
  2. pass final_run=True / --final-run to the study entry point
  3. the run executes ONCE; the flag file is deleted by the caller afterwards.
Anything else reading past the seal raises HoldoutViolationError.

Wiring status:
  - tuner/study_router.py (deployment-candidate studies): enforced NOW.
  - tuner/alpha_orchestrator.py (specialist generation loop): enforced
    Wednesday with charter gates v3 + loop migration (interim Aug-window
    diagnostics are selection-neutral: pool admission uses gates v3 scores).
"""
import os
from datetime import datetime, timezone

import pandas as pd

SEAL_DATE = datetime(2026, 7, 28, tzinfo=timezone.utc)
_FLAG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".holdout_final_run")


class HoldoutViolationError(Exception):
    """Raised when a study attempts to read data past the holdout seal."""


def guard_data_end(end, final_run: bool = False) -> pd.Timestamp:
    """Clamp/validate a requested data_end against the seal. Returns tz-aware ts."""
    e = pd.Timestamp(end)
    if e.tzinfo is None:
        e = e.tz_localize("UTC")
    else:
        e = e.tz_convert("UTC")
    if e > pd.Timestamp(SEAL_DATE):
        if final_run and os.path.exists(_FLAG_PATH):
            return e  # authorized one-shot final run
        raise HoldoutViolationError(
            f"data_end {e.isoformat()} crosses holdout seal "
            f"{SEAL_DATE.isoformat()}; authorize via {_FLAG_PATH} + final_run=True "
            f"(one-shot, logged) — or move your study window back."
        )
    return e


def authorize_final_run() -> str:
    """Create the one-shot flag. Caller MUST log this and delete after the run."""
    with open(_FLAG_PATH, "w") as f:
        f.write(datetime.now(timezone.utc).isoformat())
    return _FLAG_PATH
