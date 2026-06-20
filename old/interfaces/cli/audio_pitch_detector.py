#!/usr/bin/env python3
"""Compatibility entry point for the low-level pitch detector diagnostics CLI."""

from audio_detection.cli.audio_pitch_detector import *  # noqa: F401,F403
from audio_detection.cli.audio_pitch_detector import main


if __name__ == "__main__":
    raise SystemExit(main())
