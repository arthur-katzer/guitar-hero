# Guitar Hero Python Lab

Prototype for a terminal rhythm game and audio-analysis lab. The project has two
main use cases:

- Play a MIDI-derived chart with the keyboard.
- Compare or detect real audio against notes, chords, or a MIDI reference.

The repository intentionally keeps the game rules, audio processing, and command
line scripts separate. The game can evolve without being tied to one audio
capture approach, and the audio tools can be tested without opening the game UI.

## Quick Start

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m unittest discover -s tests
```

On Windows PowerShell, activate the virtual environment with:

```powershell
.\.venv\Scripts\Activate.ps1
```

MP3/FLAC/OGG loading depends on FFmpeg. The Python package
`imageio-ffmpeg` is installed from `requirements.txt`, but having `ffmpeg`
available on `PATH` is still useful for local troubleshooting and conversions.

## Command Map

Start here instead of trying every script.

| Goal | Command |
| --- | --- |
| Run all tests | `python -m unittest discover -s tests` |
| Convert MIDI files into game charts | `python -m minigame.cli.convert_songs` |
| Play the keyboard rhythm game | `python -m minigame.cli.play` |
| Play a specific chart | `python -m minigame.cli.play data/songs/json/arctic_monkeys-505.json data/songs/mid/arctic_monkeys-505.mid` |
| Open the desktop main menu | `python -m interfaces.gui.app` |
| Compare audio performance to MIDI | `python -m audio_detection.cli.compare_audio_to_midi --audio data/samples/arctic_monkeys-505.mp3 --midi data/songs/mid/arctic_monkeys-505.mid --out var/artifacts/505_chroma_report.csv` |
| Convert MP3 to WAV | `python -m audio_detection.cli.mp3_to_wav data/samples/arctic_monkeys-505.mp3 var/artifacts/arctic_monkeys-505.wav --overwrite` |
| List audio devices for live tools | `python -m audio_detection.cli.live_note_trainer --list-devices` |
| Scan devices for signal level | `python -m audio_detection.cli.mic_device_scan --seconds 2` |
| Practice matching live single notes | `python -m audio_detection.cli.live_note_trainer --notes A4 --hold-seconds 0.6` |
| Test a live chord/chroma target | `python -m audio_detection.cli.live_chroma_test --target C,E,G --once` |

Every CLI script also supports `--help`. Compatibility wrappers for older script
names live under `interfaces/cli/`; no Python entry points are kept in the
repository root.

## Project Layout

```text
audio/                         Audio loading, DSP, chroma comparison, note helpers
audio_detection/cli/           Audio detection, capture, conversion, and comparison CLIs
data/samples/                  Local audio samples used for manual experiments
data/songs/mid/                MIDI references
data/songs/json/               Generated rhythm-game charts
docs/adr/                      Architecture decision records
interfaces/cli/                CLI interface adapters and compatibility wrappers
interfaces/gui/                PySide6 desktop main menu
interfaces/throwaway/          Previous PySide6 GUI scaffold kept out of the current UI path
minigame/cli/                  Terminal minigame entry points
minigame/runtime/              Rhythm-game engine and curses terminal UI
tests/                         Unit tests for audio, device selection, and trainers
var/artifacts/                 Generated CSV, PNG, JSON, and WAV outputs
interfaces/cli/main.py         Compatibility wrapper for `minigame.cli.play`
interfaces/cli/*.py            Compatibility wrappers for older CLI script names
```

## Main Workflows

### 1. Run The Keyboard Game

Generate charts from every MIDI in `data/songs/mid/`:

```bash
python -m minigame.cli.convert_songs
```

Then start the game:

```bash
python -m minigame.cli.play
```

The game lists available charts from `data/songs/json/`. Press the displayed lane
keys in time with the falling notes. Press `q` to quit.

You can bypass the picker:

```bash
python -m minigame.cli.play data/songs/json/arctic_monkeys-505.json data/songs/mid/arctic_monkeys-505.mid
```

MIDI playback uses `fluidsynth` with this default soundfont path:

```text
/usr/share/soundfonts/FluidR3_GM.sf2
```

If the game opens but you hear no MIDI audio, install/configure `fluidsynth` and
the soundfont for your operating system.

### Desktop Main Menu

Open the PySide6 desktop main menu:

```bash
python -m interfaces.gui.app
```

This GUI is currently the top-level menu only. It exposes Play, Training,
Library, and Style as selectable options without opening destination screens
yet.

### 2. Compare Audio Against A MIDI Reference

Use this when you have a recorded performance and want a rough harmony/timing
match against a MIDI file:

```bash
python -m audio_detection.cli.compare_audio_to_midi \
  --audio data/samples/arctic_monkeys-505.mp3 \
  --midi data/songs/mid/arctic_monkeys-505.mid \
  --out var/artifacts/505_chroma_report.csv
```

Outputs:

- CSV report at the `--out` path.
- PNG similarity plot beside the CSV, unless `--no-plot` is passed.
- Terminal summary with mean similarity and match/weak/mismatch timeline.

Use DTW when audio and MIDI are musically similar but not aligned at the same
tempo:

```bash
python -m audio_detection.cli.compare_audio_to_midi \
  --audio data/samples/arctic_monkeys-505.mp3 \
  --midi data/songs/mid/arctic_monkeys-505.mid \
  --out var/artifacts/505_chroma_report.csv \
  --alignment dtw
```

Useful inspection commands:

```bash
python -m audio_detection.cli.compare_audio_to_midi --help
python -m audio_detection.cli.compare_audio_to_midi --audio data/samples/arctic_monkeys-505.mp3 --midi data/songs/mid/arctic_monkeys-505.mid --no-plot
```

### 3. Practice Live Single Notes

List available devices:

```bash
python -m audio_detection.cli.live_note_trainer --list-devices
```

Run a minimal A4 smoke test:

```bash
python -m audio_detection.cli.live_note_trainer --notes A4 --hold-seconds 0.6
```

Use a specific device when auto-selection is wrong:

```bash
python -m audio_detection.cli.live_note_trainer --device 14 --notes A4 --threshold 0.001 --hold-seconds 0.6
```

Practice a note pool:

```bash
python -m audio_detection.cli.live_note_trainer --first-note A4 --notes C4,D4,E4,F4,G4,A4,B4,C5
```

### 4. Test Live Chords / Pitch Classes

`audio_detection.cli.live_chroma_test` compares captured audio to pitch classes.
Examples:

- `0,4,7` means C major by pitch-class number.
- `C,E,G` means the same target by note name.

```bash
python -m audio_detection.cli.live_chroma_test --target C,E,G --once
python -m audio_detection.cli.live_chroma_test --target 0,4,7 --device 1
```

If you omit `--target`, the script asks for it interactively.

### 5. Diagnose Microphone Or System Audio

Scan devices and print signal-level diagnostics:

```bash
python -m audio_detection.cli.mic_device_scan --seconds 2
```

Scan selected devices:

```bash
python -m audio_detection.cli.mic_device_scan --devices 1,2,7,8,14,15 --seconds 2
```

Use Windows Stereo Mix / `Mixagem estéreo` when testing audio played by the
computer itself:

```bash
python -m audio_detection.cli.mic_device_scan --system-audio --seconds 2
python -m audio_detection.cli.live_note_trainer --system-audio --notes A4 --threshold 0.001 --hold-seconds 0.6
```

## Script Reference

### `audio_detection.cli.compare_audio_to_midi`

Offline chroma comparison between an audio file and MIDI reference.

Common options:

- `--audio`: MP3/WAV/FLAC/OGG input.
- `--midi`: reference MIDI input.
- `--out`: CSV report path. Defaults to `var/artifacts/chroma_report.csv`.
- `--alignment fixed|dtw`: fixed-time comparison or dynamic time warping.
- `--no-plot`: skip PNG output.
- `--include-drums`: include MIDI channel 10 percussion.

### `audio_detection.cli.live_note_trainer`

Live single-note trainer. It asks for target notes and awards a point after the
target is detected continuously for `--hold-seconds`.

Common options:

- `--list-devices`
- `--device <index-or-name>`
- `--system-audio`
- `--notes A4` or `--notes C4,D4,E4,F4,G4,A4,B4,C5`
- `--threshold 0.001`
- `--hold-seconds 0.6`

### `audio_detection.cli.live_chroma_test`

Live pitch-class matcher for chords or note sets.

Common options:

- `--target C,E,G` or `--target 0,4,7`
- `--once`
- `--list-devices`
- `--device <index-or-name>`

### `audio_detection.cli.mic_device_scan`

Records short clips from input devices and reports RMS, peak level, and pitch
diagnostics. By default it may save WAV/CSV diagnostics under `var/artifacts/`.

Common options:

- `--list-devices`
- `--devices 1,2,3`
- `--system-audio`
- `--seconds 2`
- `--no-save`

### `audio_detection.cli.audio_pitch_detector`

Older low-level pitch detector for recording, realtime pitch estimates, and FFT
diagnostics. Keep it for debugging detector behavior; prefer
`audio_detection.cli.live_note_trainer` for the current practice workflow.

Common options:

- `--list-devices`
- `--record 5 --output var/artifacts/test.wav`
- `--realtime`
- `--diagnose`
- `--compare`
- `--guitar-reference`

### `audio_detection.cli.mp3_to_wav`

Converts MP3 input to WAV.

```bash
python -m audio_detection.cli.mp3_to_wav input.mp3 output.wav --overwrite
```

## Tests

Run the whole suite:

```bash
python -m unittest discover -s tests
```

Run one test file:

```bash
python -m unittest tests.test_chroma_compare
```

The tests are meant to challenge the behavior of audio helpers, device
selection, and live-trainer logic without requiring a real microphone in normal
unit-test runs.

## Troubleshooting

### `No songs found in data/songs/json/`

Run:

```bash
python -m minigame.cli.convert_songs
```

The converter reads `.mid` files from `data/songs/mid/` and writes missing
`.json` charts to `data/songs/json/`.

### MP3 Loading Fails

Install FFmpeg and verify it is visible:

```bash
ffmpeg -version
```

As a workaround, convert the MP3 to WAV:

```bash
python -m audio_detection.cli.mp3_to_wav data/samples/arctic_monkeys-505.mp3 var/artifacts/arctic_monkeys-505.wav --overwrite
```

### Live Tools Show `Silence`

First scan devices while making sound:

```bash
python -m audio_detection.cli.mic_device_scan --seconds 2
```

Then pass the device with the strongest RMS/peak:

```bash
python -m audio_detection.cli.live_note_trainer --device 14 --notes A4 --threshold 0.001 --hold-seconds 0.6
```

### MIDI Game Has No Sound

The terminal UI can still run without audible MIDI, but playback needs
`fluidsynth` and a General MIDI soundfont. On Linux, the current code expects:

```text
/usr/share/soundfonts/FluidR3_GM.sf2
```

## Definition Of Done For The Current Prototype

- MIDI files can be converted into playable JSON charts.
- The terminal game can load a chart and handle keyboard hits/misses.
- An audio recording and MIDI of the same passage should score higher than an
  unrelated MIDI.
- Offline comparison produces a CSV, optional plot, and timeline summary.
- Live tools can detect whether captured input roughly matches a target note or
  pitch-class set.
