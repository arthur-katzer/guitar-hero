# 0006 - Low-string open-family detection

## Status

Accepted

## Test Performed

Real Sandbox trials suggested that multi-string open plucks containing lower
strings can be uneven: D3 and G3 are often easier to see than E2 and A2. We
focused the synthetic scoring checks on the requested diagnostic cases:

- E2+A2+D3+G3
- E2+A2+D3+G3+B3+E4

The synthetic cases intentionally keep E2 and A2 fundamentals weak while leaving
their 1x or 2x anchors present. They validate scoring behavior only; they do
not prove full real-guitar capture performance.

## Expected Behavior

When E2 or A2 has visible 1x or 2x anchor evidence, the Open String Families
diagnostic should not make that family disappear just because upper harmonics
overlap higher strings. D3 and G3 should remain active when their own
fundamentals and low-order harmonics are present.

When E2 or A2 has only upper harmonics and no anchor near 1x or 2x, it should
not become active. That constraint preserves the subharmonic hallucination fix
from ADR 0004.

## Observed Behavior

The previous scoring was conservative enough to avoid E4 falsely activating
A2, but it did not explain low-string evidence clearly. If E2 or A2 was weak,
the UI could not tell whether the spectrum lacked the expected low-frequency
peaks or whether the scoring policy rejected weak evidence that was actually
present.

## Root Cause Hypothesis

Low open-string fundamentals are harder to preserve in multi-string captures:

- E2 and A2 fundamentals are low-frequency peaks.
- Their fundamentals may be weaker than upper harmonics.
- Their harmonics overlap higher-string fundamentals.
- Keeping only the strongest few FFT peaks can hide weak low anchors.

## Decision

Improve low-string diagnostics without making E2 and A2 easy to activate:

- Keep active status anchored to direct 1x evidence or strong 2x evidence plus
  another low-order harmonic.
- Allow weak 1x/2x matches only for E2 and A2 so weak anchors can keep those
  families visible as uncertain or active when broader evidence supports them.
- Do not allow 3x, 4x, 5x, or 6x alone to activate E2 or A2.
- Add low-string trace text for E2 and A2 showing whether 1x through 6x are
  present, weak, or missing.
- Preserve more FFT peaks per frame for the detector while the visible Top
  Peaks panel can still show only the first few.

## Consequences

The Sandbox can now answer whether E2/A2 are missing because the captured
spectrum lacks anchor evidence or because the detector rejected weak evidence.
The behavior remains conservative: weak low-string anchors may produce
uncertain rather than active, and upper harmonics alone still do not activate
E2 or A2.

This does not add chord recognition, fretted note detection, Play/Learn
integration, export files, or reporting infrastructure.
