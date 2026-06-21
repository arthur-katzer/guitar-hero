# 0007 - Open-string co-present overlap

## Status

Accepted

## Test Performed

A manual real-capture matrix of two-string open plucks was reviewed as tuning
evidence, not as a table of cases to hardcode. Most two-string tests showed the
played strings as active, which suggests the Open String Families diagnostic is
useful. The remaining failures were concentrated around harmonically related
open strings:

- B3 is close to E2's 3x harmonic.
- E4 is close to E2's 4x harmonic.
- E4 is close to A2's 3x harmonic.

Synthetic regression tests were added for the general pattern: a higher open
string whose 1x fundamental overlaps a lower active string's harmonic, with
additional independent low-order harmonic support.

## Expected Behavior

Overlap is expected and should not by itself imply that a string was played.
However, direct 1x evidence for a higher open string should not be discarded
automatically just because a lower active string can also explain that
frequency as an upper harmonic.

The detector should distinguish:

- explained overlap: evidence is probably only a harmonic of an already active
  string.
- co-present overlap: an overlapped 1x/2x anchor also has independent harmonic
  support, so the higher string may really be present.

## Observed Behavior

After the subharmonic hallucination guard, the detector became too aggressive
at suppressing some played higher strings. In cases such as E2+B3, E2+E4, and
A2+E4, the higher string could be marked harmonic overlap because its
fundamental was first explained as a lower-string harmonic.

The opposite failure also appeared during synthetic checks: if the detector
accepted any later harmonic as co-present support, B3 could become active in an
E2+E4 pluck because B3's 4x aligned with E4's harmonic content. That is not
strong enough evidence that B3 was played.

## Root Cause Hypothesis

The previous overlap rule treated lower-string explanations as subtractive:
once a lower active string explained a peak, that peak was removed from the
higher candidate's independent evidence. This correctly prevented some false
positives, but it also erased real co-present fundamentals.

The scoring needed a middle path: retain overlapped anchors only when there is
nearby independent support from the same higher-string family.

## Decision

Keep overlap conservative, but add co-present anchor recovery:

- An overlapped 1x or 2x anchor can contribute to the higher string only if the
  candidate also has independent support near 2x or 3x, or multiple independent
  low-order harmonics.
- A sole late harmonic such as 4x is not enough to recover an overlapped anchor.
- Upper-harmonic-only evidence still cannot activate a lower string.
- The E4-vs-A2 subharmonic hallucination guard remains intact.

This is a scoring rule, not a pair-specific exception. It applies to any open
string candidate whose direct anchor overlaps an already active lower family.

## Consequences

Played higher strings in harmonically related pairs can now remain active when
they have independent support. Unplayed strings whose evidence is only a
late-harmonic coincidence remain harmonic overlap or inactive.

The numeric score is still status-dependent and should not be read as a
cross-status probability. This decision improves the detector's open-string
diagnostic behavior; it does not add chord recognition, fretted notes, machine
learning, or Play/Learn integration.
