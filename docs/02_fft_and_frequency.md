# 02 - FFT And Frequency

## Goal

Understand that FFT converts a short audio window from time-domain samples into
frequency-domain energy.

Time-domain asks: "What did the waveform do over time?"

Frequency-domain asks: "Which frequencies are strong in this window?"

## Run

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode fft --window-ms 200
```

For a cleaner learning check, use a short single-note WAV when available:

```bash
python -m tools.audio_lab --file path/to/single-note.wav --mode fft --window-ms 200
```

If a file starts with silence, choose a later window:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 200 --start-sec 2.0
```

## What To Look For

- `peak_frequency`: the strongest FFT frequency in the guitar range.
- `hps_frequency`: a Harmonic Product Spectrum estimate, useful later for real
  instruments with strong harmonics.
- `confidence`: a rough score for how concentrated the frequency peak is.
- `Strongest FFT peaks`: the ranked frequency regions found in the same window.

The FFT will often show several strong frequencies. On real instruments, the
lowest musically meaningful peak is usually the fundamental, and higher peaks
are harmonics.

Use both views:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0
```

Use only the concise detector view:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --peaks 0
```

Save a spectrum image:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --plot-out artifacts/a4_fft.png
```

Save and open the image:

```bash
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --plot-out artifacts/a4_fft.png --open-plot
```

## Teach-Back Check

Before moving on, explain this in your own words:

> FFT shows which frequencies are strong.

Write your answer in `docs/checkpoints.md` under Checkpoint 2.
