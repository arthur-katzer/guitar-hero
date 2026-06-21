# 0005 - Open-string overlap scoring calibration

## Status

Accepted

## Test Performed

We exercised the Open String Families detector with synthetic evidence for the
supported diagnostic scope:

- single strings: E2, A2, D3, G3, B3, E4
- adjacent pairs: E2+A2, A2+D3, D3+G3, G3+B3, B3+E4

The goal was not to build an evaluation framework. The test was a focused check
of the detector's current scoring rules against the specific Sandbox use case.

## Expected Behavior

Single-string captures should mark the played open string active and avoid
marking other families active from shared harmonics. Adjacent-pair captures
should keep both real families visible as active when their fundamentals and
low-order harmonics are present.

Overlapping evidence should remain explainable, but the detector should prefer
conservative uncertainty over false positives.

## Observed Behavior

The detector handled the E4/A2 subharmonic case after ADR 0004, but another
noise path remained. In a G3+B3 pair, D3 could become uncertain from D3's 4x and
5x matches alone:

- D3 4x is near a G3 harmonic.
- D3 5x is near a B3 harmonic.
- D3 had no direct 1x or 2x anchor.

This was plausible-looking output, but it was not useful evidence that D3 was
physically present.

## Root Cause Hypothesis

The uncertain threshold was too permissive for late harmonic-only evidence.
The score model also gave 5x and 6x enough weight that a family with no anchor
could appear meaningfully present.

## Decision

Keep direct fundamentals and low-order anchors as the center of the diagnostic:

- Active still requires strong score plus anchor evidence.
- Uncertain now requires partial anchor evidence: 1x, 2x, or at least three
  independent low-order harmonics.
- 5x and 6x carry much less weight than 1x, 2x, 3x, and 4x.
- Harmonic-only matches remain in debug text, but they do not automatically
  promote a family to uncertain.

## Consequences

The detector is more conservative and less noisy. Some weak real strings may
remain inactive until their 1x, 2x, or multiple low-order harmonics are visible,
but that is acceptable for the current Sandbox diagnostic because false
positives are more damaging than missed weak evidence.

This does not solve chord recognition, fretted notes, alternate tunings, or
Play/Learn scoring. It only improves open-string family diagnostics.
