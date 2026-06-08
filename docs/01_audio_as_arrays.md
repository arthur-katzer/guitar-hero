# 01 - Audio As Arrays

## Goal

Understand that digital audio is a sequence of numbers sampled over time.

If the project ever feels mysterious, come back here: the input to every
detector is just a NumPy array plus a sample rate.

## Run

```bash
python -m tools.audio_lab --file samples/Exploder.mp3 --mode summary
```

For a WAV file, use the same command with that path:

```bash
python -m tools.audio_lab --file path/to/single-note.wav --mode summary
```

MP3/FLAC/OGG decoding requires `ffmpeg` on the machine. WAV files can be read
directly through Python.

## What To Look For

- `sample_rate`: how many samples are recorded per second.
- `samples`: how many numbers are in the audio array.
- `duration`: `samples / sample_rate`.
- `rms`: a simple volume estimate. Higher RMS usually means louder audio.

## Teach-Back Check

Before moving on, explain this in your own words:

> Audio is an array of samples over time.

Write your answer in `docs/checkpoints.md` under Checkpoint 1.
