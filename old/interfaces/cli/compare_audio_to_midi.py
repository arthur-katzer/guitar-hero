#!/usr/bin/env python3
"""Compatibility entry point for the audio-vs-MIDI comparison CLI."""

from audio_detection.cli.compare_audio_to_midi import main


if __name__ == "__main__":
    raise SystemExit(main())
