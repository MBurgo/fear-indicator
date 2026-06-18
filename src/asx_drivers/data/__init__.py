"""Data loading for the ASX Drivers Index.

Phase 0 sources (all free, all keyless):
  - AUD/USD, 10y & 2y CGS yields  -> asx_mood.data.rba  (RBA F11.1, F2)
  - US HY credit spread, gold      -> asx_drivers.data.fred  (FRED fredgraph CSV)

Calendar alignment is shared with the ASX Mood Index (``asx_mood.data.align``):
RBA and FRED have different holiday calendars (and FRED carries US holidays), so
an outer join plus a short forward-fill prevents a one-source holiday from
injecting a fake move.
"""

from __future__ import annotations

from asx_mood.data import align

__all__ = ["align"]
