# Human Checkpoints

This file is intentionally part of the project. The code is not the only
deliverable: the human has to understand the system well enough to explain it.

Fill in each checkpoint after running the command and inspecting the output.

## Checkpoint 1 - Audio Basics

Command:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode summary
```

Human explanation:

```text
Audio, when seen as a waveform, is a graph: time is the X axis and amplitude is
the Y axis. Each sample is one amplitude value at one moment. A single point
does not tell us the frequency, but after enough samples we can identify
patterns over time and infer frequency.
```

Approved to continue? `yes`

## Checkpoint 2 - FFT Basics

Command:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode fft --window-ms 200
```

If the first window is silence, use `--start-sec` to inspect a later part of
the file.

Human explanation:

```text
FFT takes a window of waveform samples and converts it from amplitude-over-time
into frequency-strengths. In the FFT graph, the X axis is frequency in Hz and
the Y axis is relative magnitude, meaning how strong each frequency is compared
to the strongest frequency in that window.

A peak in the graph means that frequency is strongly present in the analyzed
audio window. The tallest peak is reported as peak_frequency, but it is not the
only frequency present and it is not the highest frequency. Smaller peaks can be
harmonics, other real sounds, noise, or artifacts. At this stage, we should not
blindly discard them as noise.

The window size matters. If the window is too large, like a whole song, the FFT
collapses too much time into one spectrum and loses when things happened. A
shorter window shows which frequencies are strong during that specific slice of
audio.
```

Approved to continue? `yes`

## Checkpoint 3 - Frequency To Note

Command:

```bash
python -m unittest discover -s tests
```

Human explanation:

```text
TODO: Explain how Hz becomes a MIDI note number and a note name.
```

Approved to continue? `no`

## Checkpoint 4 - Real Audio

Command:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode notes --window-ms 100 --hop-ms 50
```

Use `--limit 0` only if you intentionally want to inspect every detected window.

Human explanation:

```text
TODO: Explain where the detector looks confident, uncertain, or wrong.
```

Approved to continue? `no`

## Checkpoint 5 - MIDI Matching Readiness

Command:

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode match --chart songs/json/98137.json --window-ms 100 --hop-ms 50 --hit-window 0.25 --json-out artifacts/match_98137.json
```

Human explanation:

```text
TODO: Explain how detected MIDI notes will eventually be compared to chart MIDI notes.
```

Approved to continue? `no`
