# 0009 - Learn piano roll and track controls

## Status

Accepted

## Context

Learn is for studying a selected song section. The previous Learn timeline
showed target blocks, but it still pushed the screen toward a performance-lane
mental model. That is the wrong product direction for Learn because the user
needs to inspect pitches, timing, accompaniment, and a manually chosen practice
region before playing.

MIDI files often contain separate melody, bass, guitar, and accompaniment
tracks. The app does not yet have a reliable product rule for detecting the
guitar or practice track automatically.

## Decision

Learn uses a piano-roll timeline:

- vertical axis: MIDI pitches
- horizontal axis: time and measure context
- note rectangles: MIDI note spans from visible tracks
- playhead: current practice time
- start/end handles: selected practice region

Track visibility and MIDI audibility are independent. A track can be visible
but muted, or hidden but audible. Visible and audible are both enabled by
default because the common study case is to see and hear all loaded context.

Only the manually selected target track generates `LearnTarget` values. Other
tracks may stay visible or audible as study context and accompaniment, but they
do not affect target matching.

Filtered MIDI playback is an adapter detail. Learn computes the audible track
set and region, then asks an audio adapter to render a short MIDI file for the
player process. The controller still consumes only sections, regions, targets,
and detected notes.

## Consequences

Learn no longer builds or evolves a performance highway. That UI direction is
reserved for a future Play mode.

Manual target selection avoids false confidence from guessing the wrong MIDI
part. Auto-detection remains intentionally deferred until there is a concrete
rule and test data for it.

The piano roll can show accompaniment context without changing the core Learn
matching policy.
