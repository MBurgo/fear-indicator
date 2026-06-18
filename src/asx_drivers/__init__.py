"""ASX Drivers Index - a free-sourced gauge of the forces driving Australian shares.

Phase 0: four fully-daily, free, redistribution-clean components (export commodity
via gold, AUD risk flow, yield-curve slope, global credit risk) through the shared
ASX Mood Index normalisation engine. See docs/asx-drivers-spec.md.
"""

from __future__ import annotations

from . import components, index
from .index import build

__all__ = ["components", "index", "build"]

__version__ = "0.1.0"

TITLE = "ASX Drivers Index"
TAGLINE = (
    "Are the forces that drive Australian shares - commodities, the dollar, rates "
    "and global credit - a tailwind or a headwind? A conditions gauge for AU "
    "investors, not a trading signal."
)
