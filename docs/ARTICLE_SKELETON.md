# Article / Report Skeleton

This is a ready structure for a final report.

## Title

Offline DSP Foundation for a Guitar-Hero-Style Instrument Recognition Prototype

## 1. Introduction

- Motivation: rhythm game interaction with real instruments.
- Initial concept: compare played notes/chords against MIDI chart events.
- Constraint: this prototype focuses on offline analysis, not live scoring.

## 2. Background

- Digital audio as arrays of amplitude samples.
- Sample rate and duration.
- FFT as frequency-domain analysis.
- Harmonics and why real instruments create multiple peaks.
- MIDI note numbering and equal-tempered tuning.
- Chroma features for chord estimation.

## 3. Methodology

- Audio loading:
  - WAV through Python/scipy.
  - MP3/other formats through ffmpeg/ffprobe.
- Summary mode:
  - sample rate, samples, duration, RMS.
- FFT mode:
  - one window, strongest peak, HPS estimate, ranked peaks, spectrum plot.
- Notes mode:
  - sliding window note timeline.
- Chord mode:
  - chroma vector plus template matching.
- Tests:
  - synthetic A4, C4, E2, silence, noisy A4, timestamps, synthetic C major.

## 4. Results

Include:

```bash
python -m unittest discover -s tests
python -m tools.audio_lab --file samples/A4.mp3 --mode fft --window-ms 2000 --start-sec 2.0 --plot-out artifacts/a4_fft.png
python -m tools.audio_lab --file samples/Exploder.mp3 --mode chord --window-ms 2000 --start-sec 12.0 --plot-out artifacts/exploder_chroma.png
```

Discuss:

- A4 was detected near 440 Hz.
- FFT plot shows fundamental plus harmonics.
- Full-song FFT is not musically reliable because it collapses time.
- Chord detection can produce plausible candidates but is not reliable scoring.

## 5. Limitations

- Dominant pitch candidate is not always the played note.
- Full mixes are ambiguous.
- Chord recognition lacks a measured dataset.
- Live microphone/audio-interface latency was not implemented.
- Game integration remains future work.

## 6. Future Work

- Build a recorded chord dataset.
- Add confusion matrix and accuracy measurements.
- Add live audio input with latency measurement.
- Integrate instrument mode with `game/engine.py`.
- Compare detected MIDI against chart MIDI inside a hit window.

## 7. Conclusion

The project reached a working offline DSP lab and preserved the keyboard rhythm
game. It demonstrates the technical path toward instrument mode but does not yet
claim reliable live scoring.
