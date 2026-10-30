"""Production wiring for GeoResponse.

Everything here is real transport/runtime code.  It is disabled until the
operator supplies credentials or hardware; it never silently pretends to be
live.  `doctor()` reports exactly what is configured.
"""

from __future__ import annotations

from .config import Settings, get_settings

__all__ = ["Settings", "get_settings"]
