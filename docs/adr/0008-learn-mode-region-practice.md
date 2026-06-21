# 0008 - Learn mode region practice

## Status

Accepted

## Context

The app now has three product-level meanings:

- Sandbox answers "what am I playing?"
- Learn teaches a selected part of a song.
- Play will later test the user full-speed like Guitar Hero.

Sandbox already owns live guitar detection and diagnostics. The old prototype
has MIDI/chart utilities, but no current Learn use case. The first Learn
implementation needs to practice real MIDI-derived material without turning
into Play mode or depending on the experimental Open String Families diagnostic.

## Decision

Learn is a separate screen and use case from Sandbox and future Play. It uses a
MIDI-derived target timeline, where each target is a note group produced by
grouping MIDI note starts that occur close together.

The user chooses a practice region manually with two timeline handles. Automatic
MIDI section detection is intentionally deferred because there is no stable
product rule yet for what counts as a verse, riff, or phrase in arbitrary MIDI
files.

When a MIDI file has multiple playable tracks, Learn requires an explicit track
choice. Defaulting to the first melodic track would make the app feel like it
loaded a song while actually teaching the wrong part, especially in files with
separate melody, bass, guitar, and solo tracks.

Learn supports two timing policies:

- Wait Mode advances target-by-target only after the current target is matched.
- Run Mode advances the playhead in wall-clock time after a configurable
  count-in and reports timing feedback.

Run Mode approximates Play timing but does not introduce Play scoring, full-song
testing, audio playback, or Guitar Hero fail/pass rules. Those remain future
use cases.

The live detector boundary is shared between Sandbox and Learn. Sandbox remains
the diagnostic screen, while Learn consumes only pluck-level MIDI note events
for target matching.

## MIDI Target Grouping

MIDI note-on events whose start times are within a small tolerance are grouped
into one `LearnTarget`. The default tolerance is 50 ms, inside the requested
30-60 ms range.

This turns near-simultaneous note starts such as E2, B2, and E3 into one target
instead of three separate teaching steps. The target keeps all expected MIDI
notes so the UI can show a per-note checklist.

## Chord Support

Chord and multi-note support is partial in this first version. The detector
still emits single pluck-level notes reliably, while full chord recognition and
open-string family evidence remain experimental diagnostics.

Single-note and two-note targets require all expected notes. Targets with three
or more notes pass when at least 70 percent of expected notes have been
detected. This allows Learn to teach multi-note gestures without blocking the
MVP on perfect chord recognition.

## Consequences

Learn can display and practice real MIDI-derived material today, including
selected regions and basic timing feedback.

Manual region handles keep phrase selection under user control and defer
automatic arrangement analysis until there is a concrete product rule.

The shared detector boundary prevents Learn from importing Sandbox as a feature,
but keeps existing Sandbox imports working through a compatibility module.

Play mode is still unimplemented by design. Run Mode exists only as practice
timing inside a selected region.
