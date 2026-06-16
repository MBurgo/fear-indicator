"""ASX Mood Index - a Fear & Greed-style sentiment gauge for the Australian market.

Phase 0: four free, no-key components (momentum, realised volatility, safe haven,
AUD risk-on flow) through a shared z-score normalisation engine.
"""

from __future__ import annotations

from . import components, composite, index, normalise
from .composite import Reading, latest_reading
from .index import build

__all__ = [
    "components",
    "composite",
    "index",
    "normalise",
    "build",
    "latest_reading",
    "Reading",
]

__version__ = "0.1.0"
