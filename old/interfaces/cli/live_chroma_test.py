#!/usr/bin/env python3
"""Compatibility entry point for the live chroma/chord test CLI."""

from audio_detection.cli.live_chroma_test import *  # noqa: F401,F403
from audio_detection.cli.live_chroma_test import main


if __name__ == "__main__":
    raise SystemExit(main())
