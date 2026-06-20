#!/usr/bin/env python3
"""Compatibility entry point for the microphone device scan CLI."""

from audio_detection.cli.mic_device_scan import *  # noqa: F401,F403
from audio_detection.cli.mic_device_scan import main


if __name__ == "__main__":
    raise SystemExit(main())
