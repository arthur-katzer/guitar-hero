#!/usr/bin/env python3
"""Compatibility entry point for the live single-note trainer CLI."""

from audio_detection.cli.live_note_trainer import *  # noqa: F401,F403
from audio_detection.cli.live_note_trainer import main


if __name__ == "__main__":
    raise SystemExit(main())
