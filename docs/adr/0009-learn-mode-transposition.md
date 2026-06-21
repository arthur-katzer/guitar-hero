# 0009 - Learn mode transposition

## Status

Accepted

## Context

Learn mode uses MIDI tracks as candidate charts. Internet MIDI files are not
absolute truth: a selected track can be consistently shifted from the guitar
tab, represent alternate tuning, or actually contain bass or another
instrument part.

The concrete failure this addresses is a track whose lowest expected note is
D2 while the playable guitar tab and standard tuning expect E2. D2 is below
the standard guitar low string, and a +2 semitone correction aligns the chart
without changing the source file.

## Decision

Learn exposes a user-controlled semitone transpose value from -12 to +12. The
default is 0 semitones.

Transposition applies only after track selection, when Learn builds the chart
used for display, target labels, expected notes, matching, and guitar-range
validation. The original MIDI file, raw parsed track notes, timing, note
durations, and selected practice region are not modified.

`LearnTarget` keeps both raw parsed notes and active transposed notes. The
controller continues to consume the active expected notes, so selected track
plus transpose becomes the source of truth for Learn practice.

Guitar-range diagnostics also run against transposed notes. A warning below
E2 therefore indicates that the corrected chart still falls below the
project's standard guitar range, while a transpose that brings D2 to E2 removes
that warning.

Learn may suggest an upward transpose when the lowest raw note is just below
E2, but it does not auto-apply the suggestion. Low notes can mean wrong track,
bass track, alternate tuning, or bad MIDI data, and the user must choose the
correction.

## Consequences

Users can correct consistent MIDI pitch offsets without destructively editing
source MIDI data or changing playback timing.

The chart after selected track plus transpose is the practice truth for Learn
mode. This does not solve arbitrary bad MIDI data; it gives the user a focused
tool for consistent semitone mismatches.

Playback rendering remains raw MIDI-region playback. If Learn later needs
transposed accompaniment audio, that should be a separate playback-adapter
decision rather than a change to chart matching policy.
