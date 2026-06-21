# 0004 - Open-string subharmonic hallucination guard

## Status

Accepted

## Context

The Open String Families panel is an experimental Sandbox diagnostic. It worked
reasonably for most single open-string tests, but a single E4 pluck exposed a
false-positive path: a real E4 fundamental near 330 Hz can also match A2's
third harmonic.

That failure mode is a subharmonic hallucination. The detector sees a real high
note fundamental and over-explains it as evidence for a lower open string. In a
single E4 capture with peaks near 330, 660, and 990 Hz, E4 should be the active
family and A2 should not become active just because 330 Hz is close to A2's 3x.

The inverse case still matters. During a real E2 or A2 pluck, a peak near
329 Hz can be an upper harmonic of the lower string. E4 should not become active
from that shared peak unless there is independent E4 evidence.

## Decision

Keep the detector conservative. Direct fundamental evidence outranks a lower
string's upper-harmonic explanation unless the lower string has its own anchor
near 1x or 2x.

An open-string family can become active only when its score is strong and it has
anchor evidence:

- direct 1x fundamental evidence; or
- strong 2x evidence plus another low-order harmonic.

Matches at 3x, 4x, 5x, or 6x remain diagnostic evidence, but they cannot make a
lower string active by themselves. If those peaks are better explained as a
higher open string's fundamental, the lower candidate is marked as overlap or
left inactive.

## Discarded Options

- Treating every harmonic match equally was discarded because it promotes E4
  fundamentals into false A2 activity.
- Always preferring the lowest matching string was discarded because it hides
  real high-string plucks.
- Adding chord detection was discarded because this rule only improves
  open-string diagnostic evidence; it does not identify fretted notes, muted
  strings, voicings, or chord names.

## Open Decisions

- The thresholds remain empirical and may need tuning from more real capture
  sessions.
- Multi-string evidence is still diagnostic only. Play/Learn scoring and chord
  recognition remain deferred.
