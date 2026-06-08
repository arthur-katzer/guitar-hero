# 05 - Confidence Metric

## What Confidence Means

In the current MVP, `confidence` is a heuristic for peak dominance.

It is not a probability that the detected note is musically correct.

Better wording:

```text
confidence = how clearly the winning frequency peak beats plausible alternatives
```

## Old Methodology

The first confidence implementation combined two ideas:

```text
contrast = peak / (peak + spectral_floor)
concentration = peak / total_spectrum_energy
confidence = weighted average of contrast and concentration
```

The line of thought was:

- If the winning FFT peak is much louder than the spectral floor, confidence
  should be high.
- If the winning peak owns a decent share of total spectral energy, confidence
  should be high.
- This tried to answer: "Is this peak strong compared to the whole spectrum?"

## Why That Was Weak

`peak / total_spectrum_energy` is unstable across different window sizes.

A longer window can include:

- silence before the note
- attack/transient
- decay
- noise
- repeated notes
- extra harmonics
- MP3 artifacts

That means confidence could swing even when the detected pitch stayed stable.
For example, A4 could stay near `440 Hz`, while confidence moved around because
the total spectrum changed.

## New Methodology

The current implementation compares the winning peak against competing peaks:

```text
peak = magnitude of strongest FFT bin
second_peak = strongest separate FFT bin after ignoring nearby bins
floor = median nonzero spectral magnitude

competitor_score = peak / (peak + second_peak)
floor_score = peak / (peak + floor)
confidence = 0.8 * competitor_score + 0.2 * floor_score
```

Nearby bins around the winning peak are ignored because one real frequency can
spread across adjacent FFT bins. Those nearby bins should not count as a
separate competitor.

The new line of thought is:

- The main question is: "Is the winning peak clearly stronger than the next
  plausible peak?"
- Penalize spectra where another separate frequency peak is also strong.
- Keep a smaller floor comparison so noisy spectra still get penalized.

## Practical Interpretation

Use confidence as a filter, not as proof.

For future game scoring, a hit should probably require:

```text
confidence >= threshold
rms >= threshold
detected midi == expected midi
timestamp inside hit window
```

The confidence score alone should not decide whether the player was correct.
