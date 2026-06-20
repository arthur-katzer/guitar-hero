# AI Rebuild Prompt: Offline Chroma Comparison

This note replaces the generated 505 comparison artifacts that used to live in
`var/artifacts/`.

## What Was There

The deleted files were exploratory outputs from an offline audio-vs-MIDI chroma
comparison prototype:

- `var/artifacts/505.wav`: WAV converted from a local 505 MP3 sample.
- `var/artifacts/505_chroma_report.csv`: frame-by-frame chroma similarity between
  the 505 audio and a matching 505 MIDI reference.
- `var/artifacts/505_vs_unrelated_report.csv`: the same audio compared against an
  unrelated MIDI reference as a negative control.
- `var/artifacts/505_chroma_similarity.png`: generated plot for the matching report.
- `var/artifacts/synthetic_a4.wav`: small generated audio smoke artifact.

They existed to test one idea: a performance audio file should score higher
against a musically related MIDI than against an unrelated MIDI when both are
reduced to 12-bin chroma timelines.

## Why They Were Removed

The idea is still useful, but the files were the wrong project shape:

- They were generated artifacts, not source.
- They were too large/noisy to review.
- They depended on ad hoc local media instead of a clean fixture.
- They made `var/artifacts/` look like canonical data instead of runtime output.
- The current scoring can over-reward shared silence, so the demo needs a more
  honest metric before it becomes evidence.

## Prompt To Rebuild This Cleanly

Use this prompt with an AI coding agent when it is time to rebuild the offline
comparison demo:

```text
We are working in the guitar-hero Python project.

Rebuild the offline audio-vs-MIDI chroma comparison demo in a clean,
reproducible way. Preserve the concept of comparing audio chroma against MIDI
chroma, but do not rely on large checked-in generated artifacts.

Current intent:
- Convert audio and MIDI into 12 pitch-class chroma timelines.
- Compare a related audio/MIDI pair against an unrelated pair.
- Show that the related pair scores higher.
- Make silence handling honest, either by excluding silent frames from the main
  score or by giving them an explicit status instead of treating mutual silence
  as musical evidence.

Constraints:
- Keep generated CSV, PNG, WAV, and JSON outputs under `var/artifacts/`.
- Do not commit generated reports or converted media.
- Prefer small synthetic fixtures or tiny deterministic generated fixtures for
  tests.
- Keep the implementation deadline-friendly: no large refactor unless needed.
- Leave README cleanup for the final documentation pass unless the task is
  specifically about README.

Suggested deliverables:
- A focused test proving related chroma timelines score higher than unrelated
  timelines.
- A small command or test fixture that can regenerate a demo report.
- Clear status labels for match, weak match, mismatch, and silence/no-signal.
- A terminal summary that reports active-frame similarity separately from any
  all-frame similarity.
- Optional plot generation, but only as a generated artifact.

Useful existing files:
- `audio/chroma_compare.py`
- `audio_detection/cli/compare_audio_to_midi.py`
- `tests/test_chroma_compare.py`
- `data/songs/mid/`
- `data/samples/`

Definition of done:
- Tests pass.
- The demo can be regenerated from source commands.
- No generated CSV, PNG, WAV, or JSON files need to be kept in git.
- The result is honest about what the prototype proves and what it does not.
```
