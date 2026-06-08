# 04 - MIDI Matching Plan

## Goal

Prepare the bridge from offline note detection to the existing rhythm game.

The current game already has chart events with this shape:

```json
{
  "time": 1.286,
  "note": "E5",
  "midi": 76,
  "key": "d"
}
```

The new detector returns the same kind of musical identity:

```json
{
  "start_time": 1.250,
  "end_time": 1.350,
  "note_name": "E5",
  "midi": 76,
  "frequency_hz": 659.26,
  "confidence": 0.82
}
```

That means instrument mode does not need to guess keyboard lanes. It can compare
detected `midi` against chart `midi`.

## Future Integration Shape

1. Keep `keyboard mode` unchanged.
2. Add `instrument mode` as a separate input source.
3. Use the existing hit window from `game/engine.py`.
4. Count a hit when:
   - detection is not silence,
   - detection confidence is above threshold,
   - detected MIDI equals expected chart MIDI,
   - detection timestamp lands inside the hit window.

## Offline Prototype

The project now has an offline matching mode:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode match --chart songs/json/98137.json --window-ms 100 --hop-ms 50 --hit-window 0.25
```

This does not make the game playable with an instrument yet. It verifies the
data flow:

```text
audio -> detected MIDI timeline -> chart MIDI events -> hit/miss summary
```

## Chords Are Future Work

Full chord detection should use chroma/template matching, similar to the
existing `experiments/chord_detection/chord_detector.py` prototype. This MVP
intentionally stops at single notes so the foundation can be tested and
understood.

## Teach-Back Check

Before touching game integration, explain this in your own words:

> The chart has expected MIDI notes, and the detector produces detected MIDI
> notes. Instrument mode will score by comparing those numbers in time.

Write your answer in `docs/checkpoints.md` under Checkpoint 5.
