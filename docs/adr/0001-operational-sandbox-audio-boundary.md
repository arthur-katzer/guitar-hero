# 0001 - Operational sandbox audio boundary

## Status

Accepted

## Context

The sandbox must integrate the old audio pitch detector with the useful
relative-magnitude/frequency peak chart from the throwaway audio lab mock. The
new screen cannot be mock-only: it must open real input devices such as the USB
Audio CODEC and analyze live buffers.

The old detector lives under `old/`, which is retained as legacy reference code.
Importing from `old/` would make the current GUI depend on archived package
layout and would collide with the current top-level `interfaces` package.

## Decision

Port the detector policy needed by the sandbox into
`interfaces/sandbox/audio_pitch.py`, keeping it independent from Qt. The Qt
screen in `interfaces/sandbox/view.py` owns only device selection, start/stop
controls, metric cards, and the relative magnitude / Hz peak table.

## Discarded Options

- Importing `old.audio_detection.cli.audio_pitch_detector` directly was
  discarded because `old/` is legacy storage and its CLI module mixes device
  access, printing, recording, and analysis concerns.
- Reusing the throwaway audio lab mock was discarded because it generates fake
  frames and does not open real audio streams.

## Open Decisions

- The sandbox currently focuses on live guitar-range pitch diagnostics. Binding
  it to game scoring, MIDI charts, or persistence remains intentionally deferred.

