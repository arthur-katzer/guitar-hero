# Final Product Guide

This guide describes the current usable product. It is intentionally honest
about limits.

## 1. What This Project Can Do

The project currently has three working surfaces:

1. Keyboard rhythm game from MIDI charts.
2. Offline audio-to-note analysis using FFT/HPS.
3. Offline chord estimation using chroma/template matching.

The audio features are analysis tools, not a finished live instrument game.

## 2. Install And Verify

Install Python dependencies:

```bash
python -m pip install --user -r requirements.txt
```

Verify the code:

```bash
python -m unittest discover -s tests
```

Expected result:

```text
OK
```

Non-WAV audio requires `ffmpeg` and `ffprobe` on the machine.

## 3. Project Layout

```text
audio/                  reusable DSP and chord detection modules
docs/                   learning docs, checkpoints, roadmap status, guide
experiments/            older prototypes and exploratory code
game/                   terminal rhythm game engine and curses UI
samples/                sample audio files used by the labs
songs/                  MIDI files and generated JSON charts
tests/                  automated tests
tools/                  command-line tools runnable with python -m
main.py                 keyboard-mode game entrypoint
```

## 4. Audio Summary

Use summary mode to check whether an audio file loads correctly:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode summary
```

It prints:

- sample rate
- sample count
- duration
- RMS volume

This does not detect notes. It validates the input.

## 5. FFT Inspection

Use FFT mode to inspect one audio window:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0
```

This prints:

- dominant pitch candidate
- MIDI note number
- strongest FFT peak
- HPS estimate
- cents deviation
- confidence
- RMS
- ranked FFT peaks

Save a spectrum image:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --plot-out artifacts/a4_fft.png
```

Save and open:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --plot-out artifacts/a4_fft.png --open-plot
```

Read the FFT graph as:

```text
X axis = frequency in Hz
Y axis = relative magnitude
Peak = frequency region strongly present in this window
```

Do not analyze a full song unless you explicitly want one collapsed spectrum.
Large windows lose timing information.

## 6. Note Timeline

Use notes mode to analyze an audio file as a sequence of windows:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --window-ms 100 --hop-ms 50
```

Export full results:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --window-ms 100 --hop-ms 50 --json-out artifacts/exploder_notes.json
```

Important:

```text
The detector estimates one dominant pitch candidate per window.
It does not prove which instrument or note is musically intended.
```

## 7. Chord Estimation

Use chord mode to run chroma/template matching on one window:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode chord --window-ms 2000 --start-sec 12.0
```

Save a chroma image:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode chord --window-ms 2000 --start-sec 12.0 --plot-out artifacts/exploder_chroma.png
```

Chord mode prints:

- estimated chord
- confidence
- RMS
- 12-note chroma energy vector

Limit:

```text
Chord mode is experimental. It is useful for learning and rough inspection,
not for reliable scoring yet.
```

## 8. Keyboard Game

## 8. Offline Chart Matching

Use match mode to compare detected audio windows against chart MIDI events:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode match --chart songs/json/98137.json --window-ms 100 --hop-ms 50 --hit-window 0.25 --json-out artifacts/match_98137.json
```

This prints:

- chart event count
- hits
- misses
- accuracy
- first match/miss rows

Important:

```text
This is a prototype bridge toward instrument mode. A bad score is expected when
matching a full song mix against a MIDI chart, because the detector is only
estimating dominant pitch candidates from mixed audio.
```

Use this mode to verify data flow:

```text
audio -> detected MIDI timeline -> chart MIDI events -> hit/miss summary
```

Do not use it as evidence that live instrument scoring is finished.

## 9. Keyboard Game

Run the existing keyboard rhythm game:

```bash
python main.py
```

Choose a song from the list and play using keyboard lanes.

This mode is separate from audio instrument detection.

## 10. Human Checkpoints

Read and fill:

```text
docs/checkpoints.md
```

The first two checkpoints have been approved during development. Remaining
checkpoints still require human review before claiming full understanding.

## 11. Recommended Demo Script

For a final demo, run:

```bash
python -m unittest discover -s tests
python -m tools.audio_lab --file samples/Exploder.mp3 --mode summary
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --plot-out artifacts/a4_fft.png
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --window-ms 100 --hop-ms 50
python -m tools.audio_lab --file samples/Exploder.mp3 --mode chord --window-ms 2000 --start-sec 12.0 --plot-out artifacts/exploder_chroma.png
python -m tools.audio_lab --file samples/Exploder.mp3 --mode match --chart songs/json/98137.json --window-ms 100 --hop-ms 50 --hit-window 0.25 --json-out artifacts/match_98137.json
python main.py
```

## 12. Honest Limits

This project should not claim full music transcription.

Weak cases:

- full chords in noisy mixes
- distorted guitar
- drums
- vocals
- multiple instruments
- strong harmonics louder than fundamentals
- octave ambiguity
- bends and vibrato
- short transients
- low-quality compressed audio

The realistic future target is:

```text
isolated instrument input -> pitch/chord estimate -> compare against MIDI chart
```

The unrealistic target is:

```text
full song mix -> identify every instrument and intended played note
```
