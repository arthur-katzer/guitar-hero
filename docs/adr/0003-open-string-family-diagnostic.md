# 0003 - Open-string family diagnostic

## Status

Accepted

## Context

The Sandbox already has a pluck-level note detector that chooses one stable note
from a short capture window. That is useful for single-string diagnostics, but
multi-string open plucks can contain evidence for more than one standard guitar
string. Collapsing that evidence into one note hides the signal we need to
inspect before attempting any broader recognition work.

Open-string harmonics overlap. A peak near 330 Hz can be the E4 open-string
fundamental, the fourth harmonic of E2, or the third harmonic of A2. Treating
every matching harmonic as an active string would overstate the detector's
certainty and make the diagnostic look like chord recognition.

## Decision

Add a Sandbox-only open-string family detector in
`interfaces/sandbox/audio_pitch.py`. It consumes the same pluck capture window
used by the note detector and scores only the six standard open strings:
E2, A2, D3, G3, B3, and E4.

The Qt Sandbox renders this as an "Open String Families" panel. The existing
single-note "Detected Note" readout remains unchanged. The new report keeps
overlap as an explicit status so a shared harmonic can remain visible without
being promoted to a definitely active string.

## Discarded Options

- Replacing the pluck-level note detector was discarded because the existing
  readout still answers a different diagnostic question: the best single-note
  interpretation of one physical pluck.
- Adding chord names was discarded because open-string evidence is not enough
  to infer chord identity, inversions, muted strings, or fretted notes.
- Sending this to Play/Learn was discarded because the current detector is an
  exploratory Sandbox diagnostic, not a scoring contract.

## Open Decisions

- Fretted notes and alternate tunings remain deferred.
- Chord recognition remains deferred until the diagnostic evidence proves that
  multi-string families are stable enough to support a stronger contract.
- Thresholds may need adjustment after real capture sessions with different
  pickups, interfaces, and rooms.
