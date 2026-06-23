#!/usr/bin/env python3
"""Root compatibility entry point for live audio pitch diagnostics.

The actively maintained GUI imports audio detection through ``interfaces``.
This file exists because the operational terminal workflow is still
``python -u audio_pitch_detector.py ...`` from the repository root, which is
faster when tuning USB input levels and harmonic detection outside the GUI.

@author Codex - restored root CLI command for realtime and diagnostic use.
"""

from audio_detection.cli.audio_pitch_detector import main


if __name__ == "__main__":
    raise SystemExit(main())
