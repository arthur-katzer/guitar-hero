# Roadmap Status

This file maps the current implementation against the roadmap.

## Phase 1 - DSP Foundation

Status: partially complete; offline foundation is strong.

Implemented:

- Read WAV/MP3/FLAC/OGG audio into arrays.
- Print sample rate, sample count, duration, and RMS.
- Run FFT on audio windows.
- Print strongest FFT peaks.
- Generate FFT spectrum PNGs.
- Convert frequency to MIDI note number and note name.
- Run note detection over a timeline.
- Automated tests for A4, C4, E2, silence, noisy note, and timestamps.

Not implemented:

- Live microphone loop as production code.
- Audio interface calibration.
- Formal measured accuracy table.
- MIDI keyboard baseline.

Roadmap checklist estimate:

```text
1.1 Environment/libs: partial; requirements exists, no committed virtualenv
1.2 First audio read: done
1.3 First FFT: done
1.4 Harmonics: partial; peaks/plots show harmonics, no formal annotation table
1.5 Frequency -> note: done
1.6 Real-time microphone: experimental only, not production
1.7 MIDI baseline: not done
```

## Phase 2 - Chord Detection

Status: partial experimental implementation.

Implemented:

- Chroma vector extraction.
- Template matching for common chord types.
- Chord CLI mode.
- Chroma energy PNG output.
- Synthetic C major test.

Not implemented:

- Real dataset of recorded chords.
- Confusion matrix.
- Accuracy per chord.
- Real-time chord capture loop.

Roadmap checklist estimate:

```text
2.1 Chroma concept: implemented in code/docs with chroma plot
2.2 Dataset: not done
2.3 Template matching: done
2.4 Evaluation/documentation: partial docs only; no measured dataset accuracy
2.5 Real-time pipeline: not done
```

## Phase 3 - Game Integration

Status: partially implemented offline; not live-integrated.

Implemented:

- Existing keyboard mode remains available.
- MIDI matching plan exists in `docs/04_midi_matching_plan.md`.
- Detector output includes `midi`, timestamps, confidence, and RMS.
- Offline chart matching mode compares detected MIDI windows against chart MIDI
  events and produces hit/miss summaries.

Not implemented:

- Instrument mode.
- Audio capture thread in the game loop.
- Scoring detected notes against chart events.
- Latency compensation.

Reason:

```text
The detector is not yet reliable enough for live scoring, and the project should
not pretend otherwise.
```

Current safe claim:

```text
The data-flow bridge exists offline: audio detections can be compared against
chart events. Live gameplay integration remains future work.
```

Roadmap checklist estimate:

```text
3.1 Connect detector to game: offline bridge only; no game loop integration
3.2 Latency: not done
3.3 Tolerance/UX: offline hit-window exists; no live UI feedback
3.4 Playability test: keyboard game exists; instrument-mode playtest not done
```

## Phase 4 - Article And Polish

Status: partially implemented.

Implemented:

- Learning docs.
- Human checkpoints.
- FFT image generation.
- Chroma image generation.
- Final usage guide.
- Roadmap status.
- Article/report skeleton.

Not implemented:

- Complete academic article.
- Formal results section.
- Confusion matrix figure.
- User study/playtest.
- Pipeline block diagram.
- Prototype screenshot capture.

Roadmap checklist estimate:

```text
4.1 Article: skeleton only, not complete
4.2 Figures: FFT and chroma figures done; block diagram/confusion matrix/screenshots not done
4.3 Delivery polish: dependency list and guide done; cross-machine test/external review not done
```

## Final Honest Claim

The current project is a working offline DSP lab plus a keyboard rhythm game.

It can demonstrate:

- audio as arrays,
- FFT frequency analysis,
- dominant pitch detection,
- chroma-based chord estimation,
- how future MIDI matching would work.

It cannot honestly claim:

- live Guitar Hero with real instrument scoring,
- reliable full-song transcription,
- reliable chord scoring from noisy or mixed audio.
