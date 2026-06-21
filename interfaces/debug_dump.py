"""Terminal debug dump boundary for local app observation.

The GUI is currently the main way to exercise audio and Learn behavior, but
terminal output is the only practical observation channel when another process
or agent is watching a live run. This module centralizes that dump so screens
can expose useful state without each inventing its own print format.
"""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
from enum import Enum
import json
import os
from pathlib import Path
import time
from typing import Any


DISABLED_VALUES = {"0", "false", "False", "off", "OFF", "no", "NO"}


def debug_dump_enabled() -> bool:
    """Return whether terminal debug dump output should be emitted.

    Local GUI runs need observable behavior by default. The environment
    variable exists for long sessions where frame dumps become noisy.

    @author Codex - created terminal debug dump boundary.
    """

    return os.environ.get("GUITAR_HERO_DEBUG_DUMP", "1") not in DISABLED_VALUES


def dump(area: str, event: str, **fields: Any) -> None:
    """Print one structured debug line to stdout.

    ``area`` names the screen or adapter, while ``event`` names the state
    transition. Field values are rendered as compact JSON-ish literals so the
    output stays readable and machine-searchable.

    @author Codex - created terminal debug dump boundary.
    """

    if not debug_dump_enabled():
        return
    timestamp = f"{time.monotonic():.3f}"
    rendered_fields = " ".join(f"{key}={_render_value(value)}" for key, value in fields.items())
    suffix = f" {rendered_fields}" if rendered_fields else ""
    print(f"[dump {timestamp} {area}] {event}{suffix}", flush=True)


def _render_value(value: Any) -> str:
    """Return a compact debug representation for one field value."""

    return json.dumps(_plain_value(value), ensure_ascii=True, separators=(",", ":"))


def _plain_value(value: Any) -> Any:
    """Convert common app values into JSON-compatible debug values."""

    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Path):
        return str(value)
    if is_dataclass(value):
        return _plain_value(asdict(value))
    if isinstance(value, dict):
        return {str(key): _plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain_value(item) for item in value]
    if isinstance(value, float):
        return round(value, 6)
    return value
