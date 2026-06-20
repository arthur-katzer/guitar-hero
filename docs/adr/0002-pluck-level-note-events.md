# 0002 - Pluck-level note events

## Status

Accepted

## Context

The sandbox explains what the instrument is doing while showing a live FFT. A
single plucked guitar string can report different dominant FFT peaks during the
same physical note because harmonic strengths shift during attack and decay. A
low E pluck may expose peaks near 81 Hz, 162 Hz, 245 Hz, and 326 Hz across
adjacent frames.

Treating each frame as a new detected note makes the GUI appear unstable. Those
frames are not different notes; they are different harmonics of the same string.

## Decision

Keep frame-level FFT analysis as live diagnostic evidence, but add a
pluck-level detector in `interfaces/sandbox/audio_pitch.py`. The detector owns a
small state machine:

- `IDLE` waits for an RMS attack.
- `CAPTURING` collects roughly 100-200 ms of FFT evidence.
- `LATCHED` holds the classified note event while the string decays.

The Qt sandbox updates spectrum widgets from every `PitchFrame`, but updates
the displayed detected note only when `PluckDetector` emits a `DetectedPluck`.
Classification scores candidates by persistence and by how consistently they
explain harmonic multiples across the capture window.

## Discarded Options

- Smoothing the displayed frame-level note was discarded because it hides the
  symptom without modeling the domain event. A pluck is the musical unit the
  user cares about, not a timer-smoothed FFT frame.
- Forcing the lowest visible peak to be the note was discarded because missing
  or noisy fundamentals are common; a harmonic series can imply the fundamental
  even when the fundamental is weak in a given frame.
- Freezing the whole detector output during decay was discarded because the FFT
  visualization should remain live for diagnostics.

## Open Decisions

- RMS attack and release thresholds are currently conservative defaults. Device
  and pickup-specific calibration remains deferred until real capture sessions
  show stable ranges.
- Retrigger behavior while a string is still ringing is intentionally strict:
  a new note event requires returning to release/silence. More aggressive
  derivative-based retriggering can be added later if the play use case needs
  repeated notes during sustain.
