# 06 - Chord Detection

## What Chord Mode Does

Chord mode estimates one chord candidate from one audio window.

It uses:

1. FFT to measure frequency energy.
2. Chroma extraction to collapse frequencies into 12 pitch classes.
3. Template matching against chord patterns.

Run:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode chord --window-ms 2000 --start-sec 12.0
```

Save a chroma plot:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode chord --window-ms 2000 --start-sec 12.0 --plot-out artifacts/exploder_chroma.png
```

## How To Read Chroma

The chroma vector has 12 values:

```text
C, C#, D, D#, E, F, F#, G, G#, A, A#, B
```

Each value estimates how much energy exists in that pitch class, ignoring
octave. For example, C3, C4, and C5 all contribute to `C`.

That makes chroma useful for chords because a C major chord should emphasize:

```text
C, E, G
```

## Template Matching

A chord template is a 12-value pattern.

Example: major chord intervals are root, major third, perfect fifth.

```text
C major = C, E, G
```

The code rotates each template through all possible roots and chooses the
highest cosine similarity.

## Honest Limits

Chord mode is experimental.

Weak cases:

- full mixes
- distorted guitars
- bass-heavy windows
- vocals
- drums
- missing fundamentals
- extra non-chord tones
- ambiguous power chords

Use chord mode to inspect and learn. Do not use it yet as final game scoring.
