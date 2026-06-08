# 03 - Pitch Detection

## Goal

Understand how a frequency becomes a musical note.

The current MVP detects one dominant note at a time. It does not detect full
chords yet.

## Formula

The detector converts Hz to MIDI with:

```text
midi = 69 + 12 * log2(frequency_hz / 440)
```

Then it rounds to the nearest MIDI note and converts that number to a readable
name like `A4`, `C4`, or `E2`.

## Run

Run the automated checks:

```bash
python -m unittest discover -s tests
```

Run a real audio timeline:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --window-ms 100 --hop-ms 50
```

Optionally export the results:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --json-out artifacts/exploder_notes.json
```

By default, the terminal shows the first 80 rows so a full song does not flood
the screen. Use `--limit 0` when you intentionally want every row printed.

## What To Look For

- `note`: detected note name.
- `midi`: detected MIDI note number.
- `hz`: detected frequency.
- `cents`: tuning offset from the nearest MIDI note.
- `conf`: rough confidence, useful for spotting uncertain windows.
- `rms`: volume for the analyzed window.

## Teach-Back Check

Before moving on, explain this in your own words:

> A detected frequency can be mapped to a MIDI note number, then to a note name.

Write your answer in `docs/checkpoints.md` under Checkpoint 3.
