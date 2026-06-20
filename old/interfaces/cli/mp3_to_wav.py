#!/usr/bin/env python3
"""Compatibility entry point for the MP3-to-WAV conversion CLI."""

from audio_detection.cli.mp3_to_wav import *  # noqa: F401,F403
from audio_detection.cli.mp3_to_wav import main


if __name__ == "__main__":
    raise SystemExit(main())
