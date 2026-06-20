# Tree Structure

This repository is organized by application responsibility, not by framework.
The application currently exposes command-line adapters and a PySide6 desktop
main menu. There is no HTTP API in this codebase.

## Root Files

- `.gitignore` - Git ignore rules for Python caches, virtual environments, and
  generated runtime outputs.
- `README.md` - User-facing setup, commands, workflows, and troubleshooting.
- `TREE_STRUCTURE.md` - This file. Explains the repository layout and the role
  of each relevant file group.
- `AI_REBUILD_PROMPT.md` - Context note for rebuilding the offline chroma
  comparison demo without committing large generated artifacts.
- `requirements.txt` - Python dependency list for local development and CLI
  execution.

The repository root should not contain Python source files. Python code belongs
inside a package directory such as `audio/`, `audio_detection/`, `minigame/`, or
`interfaces/`.

## Architecture Rules

- `audio/` contains reusable audio policy and DSP primitives.
- `audio_detection/` contains audio-detection use cases and their CLI
  implementations.
- `minigame/` contains the rhythm-game use cases and runtime.
- `interfaces/` contains external adapters. Current adapters are CLI wrappers
  and a PySide6 desktop main menu.
- `data/` contains versionable input data and generated chart data.
- `var/` contains local runtime outputs. Files here are not source policy.
- `docs/adr/` records non-obvious architecture decisions and their context.
- `tests/` challenges behavior without requiring real microphone hardware in
  normal unit-test runs.

## `audio/`

Reusable audio core. This package should not know about CLI parsing or terminal
interaction.

- `audio/__init__.py` - Public exports for common audio helpers.
- `audio/dsp.py` - Pitch detection, FFT/window analysis, MIDI/note conversion,
  and low-level signal helpers.
- `audio/chords.py` - Chord and pitch-class detection built on reusable DSP
  concepts.
- `audio/chroma_compare.py` - Chroma extraction, MIDI-to-chroma conversion,
  similarity comparison, report generation, and optional plotting.
- `audio/device_select.py` - Audio-device name normalization and system-audio
  device selection rules.
- `audio/io.py` - Audio loading helpers for WAV and ffmpeg-backed formats.

## `audio_detection/`

Audio-detection application workflows. This package is allowed to orchestrate
`audio/` primitives and expose CLI commands, but should keep reusable DSP logic
in `audio/`.

- `audio_detection/__init__.py` - Package marker for audio-detection use cases.
- `audio_detection/cli/__init__.py` - Package marker for audio-detection CLI
  commands.
- `audio_detection/cli/compare_audio_to_midi.py` - Offline audio-vs-MIDI chroma
  comparison command.
- `audio_detection/cli/live_note_trainer.py` - Live single-note practice command
  that listens until a target note is held long enough.
- `audio_detection/cli/live_chroma_test.py` - Live chord/pitch-class diagnostic
  command.
- `audio_detection/cli/mic_device_scan.py` - Input-device scan command that
  reports RMS, peak level, pitch estimate, and optional WAV/CSV diagnostics.
- `audio_detection/cli/audio_pitch_detector.py` - Lower-level pitch detector and
  FFT diagnostics command kept for detector debugging.
- `audio_detection/cli/mp3_to_wav.py` - Audio conversion helper command.

## `minigame/`

Terminal rhythm-game application. This package owns game-specific behavior and
must not depend on microphone/audio-detection workflows.

- `minigame/__init__.py` - Package marker for the rhythm minigame.
- `minigame/cli/__init__.py` - Package marker for minigame CLI commands.
- `minigame/cli/play.py` - CLI entry point for playing a MIDI-derived chart in
  the terminal.
- `minigame/cli/convert_songs.py` - Converts MIDI files from `data/songs/mid/`
  into playable chart JSON files under `data/songs/json/`.
- `minigame/runtime/__init__.py` - Package marker for runtime components.
- `minigame/runtime/engine.py` - Game timing, note hit/miss rules, scoring
  state, and MIDI playback orchestration.
- `minigame/runtime/interface.py` - `curses` terminal rendering and keyboard
  input adapter.

## `interfaces/`

External interface adapters. CLI and GUI entry points live here instead of
leaking framework concerns into the audio or minigame packages. Future
interfaces, such as HTTP, should get separate folders under `interfaces/`.

- `interfaces/__init__.py` - Package marker for interface adapters.
- `interfaces/cli/__init__.py` - Package marker for CLI adapters.
- `interfaces/cli/main.py` - Compatibility wrapper for `minigame.cli.play`.
- `interfaces/cli/compare_audio_to_midi.py` - Compatibility wrapper for
  `audio_detection.cli.compare_audio_to_midi`.
- `interfaces/cli/live_note_trainer.py` - Compatibility wrapper for
  `audio_detection.cli.live_note_trainer`.
- `interfaces/cli/live_chroma_test.py` - Compatibility wrapper for
  `audio_detection.cli.live_chroma_test`.
- `interfaces/cli/mic_device_scan.py` - Compatibility wrapper for
  `audio_detection.cli.mic_device_scan`.
- `interfaces/cli/audio_pitch_detector.py` - Compatibility wrapper for
  `audio_detection.cli.audio_pitch_detector`.
- `interfaces/cli/mp3_to_wav.py` - Compatibility wrapper for
  `audio_detection.cli.mp3_to_wav`.
- `interfaces/gui/` - Current PySide6 desktop main menu with Play, Training,
  Library, and Style options.
- `interfaces/gui/app.py` - GUI entry point for
  `python -m interfaces.gui.app`.
- `interfaces/gui/main_window.py` - Hosts the responsive main menu and keyboard
  navigation behavior.
- `interfaces/throwaway/` - Previous PySide6 GUI scaffold kept outside the
  current UI path.

## `data/`

Versionable data used by the application.

- `data/samples/` - Local audio samples used for manual experiments and command
  examples.
- `data/samples/A1.mp3` - Sample audio for A1.
- `data/samples/A4.mp3` - Sample audio for A4.
- `data/samples/arctic_monkeys-505.mp3` - Sample recording used in comparison
  examples.
- `data/samples/505 - Arctic Monkeys ... .mp3` - Additional local sample media.
- `data/songs/mid/` - MIDI references used by the minigame and comparison
  workflows.
- `data/songs/mid/arctic_monkeys-505.mid` - MIDI reference for the 505 example.
- `data/songs/json/` - Generated playable chart files for the minigame.
- `data/songs/json/arctic_monkeys-505.json` - Generated chart for the 505 MIDI
  reference.

## `var/`

Local runtime outputs. Treat this as disposable working output, not application
policy.

- `var/artifacts/` - Generated CSV, PNG, JSON, and WAV files from diagnostics,
  conversions, plots, and local experiments.

## `docs/`

Project documentation that captures decisions, not just behavior.

- `docs/adr/0001-separate-audio-detection-and-minigame.md` - Architecture
  decision record explaining why audio detection, minigame runtime, interfaces,
  data, and runtime outputs are separated.
- `docs/adr/0002-desktop-gui-as-interface-adapter.md` - Architecture decision
  record explaining why the PySide6 GUI is a scaffolded external adapter and
  why Monokai theme assets are loaded defensively.

## `tests/`

Unit tests for core behavior and CLI-supporting logic.

- `tests/test_audio_io.py` - Audio loading tests.
- `tests/test_audio_pitch_detector.py` - Low-level pitch detector and
  fundamental-estimation tests.
- `tests/test_chroma_compare.py` - Chroma conversion, comparison, DTW alignment,
  and live chroma helper tests.
- `tests/test_device_select.py` - Audio-device parsing and system-audio
  selection tests.
- `tests/test_dsp.py` - DSP pitch/chord analysis tests.
- `tests/test_live_note_trainer.py` - Note parsing and shuffled target-note
  selection tests.
- `tests/test_mic_device_scan.py` - Microphone scan signal classification and
  mono-conversion tests.
- `tests/test_gui_main_menu.py` - Current desktop main-menu option and keyboard
  navigation tests.

## Local/Generated Folders

These folders can appear during local development but are not architecture:

- `.git/` - Git repository metadata.
- `.agents/` and `.codex/` - Local agent/tooling metadata.
- `__pycache__/` folders - Python bytecode caches generated by imports/tests.
- `.venv/`, `venv/`, or `env/` - Local virtual environments, if created.
