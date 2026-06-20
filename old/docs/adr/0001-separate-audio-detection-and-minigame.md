# ADR 0001: Separate audio detection from the terminal minigame

## Status

Accepted

## Context

The repository contains two different products:

- audio detection and analysis workflows, including pitch detection, device
  diagnostics, chroma comparison, and audio conversion;
- a terminal rhythm minigame that consumes generated song charts and keyboard
  input.

Before this decision, command modules for both products lived together at the
repository root while the minigame runtime lived in `game/`. That layout made
the root look like one flat script collection and did not show which files
belonged to audio detection versus the playable CLI game.

## Decision

Use product-oriented top-level packages:

- `audio_detection/cli/` owns command-line adapters for audio detection,
  capture, conversion, and comparison workflows.
- `minigame/cli/` owns minigame entry points.
- `minigame/runtime/` owns the minigame engine and terminal UI.
- `audio/` remains the reusable audio policy/core package used by the audio
  detection CLIs.
- `data/` owns versionable inputs such as samples, MIDI files, and generated
  charts.
- `var/artifacts/` owns local runtime outputs such as CSV, PNG, JSON, and WAV
  diagnostics.
- `interfaces/cli/` owns compatibility wrappers for old script names and keeps
  executable adapter files out of the repository root.

Keep compatibility wrappers for existing command names, but store them under
`interfaces/cli/` instead of the repository root. The canonical commands are
now `python -m audio_detection.cli.<name>` and `python -m minigame.cli.play`.

## Alternatives discarded

- Keeping every CLI in the repository root was discarded because it hides the
  two product boundaries and makes new scripts harder to place consistently.
- Renaming the reusable `audio/` package to `audio_detection/` was discarded
  because `audio/` contains reusable DSP and IO primitives, while
  `audio_detection/cli/` is only an adapter layer for workflows.
- Deleting compatibility wrappers immediately was discarded because local habits
  may still depend on those script names. Keeping them in `interfaces/cli/`
  preserves the adapter without allowing Python files to accumulate in the
  repository root.

## Open decisions

Packaging and distribution are intentionally deferred. The project does not yet
need console scripts in `pyproject.toml`; `python -m ...` keeps the entry points
explicit without introducing packaging decisions before they are required.
