# ADR 0002: Desktop GUI as an interface adapter

## Status

Accepted

## Context

The project now needs a PySide6 desktop GUI so the Tuner / Training and Player /
Hero workflows can be inspected visually. The core audio and rhythm-game
packages already have separate responsibilities: `audio/` owns reusable DSP and
IO primitives, `audio_detection/` owns audio-detection workflows, and
`minigame/` owns gameplay runtime behavior.

The GUI request is intentionally a scaffold. It must show shell navigation,
placeholder panels, plots, and settings without opening audio streams, parsing
MIDI, or implementing gameplay.

Local Monokai Pro JSON and HTML assets exist outside the repository under
`/home/katzer/dev/bin/`. Those assets are useful for visual fidelity, but they
are developer-local files rather than application-owned source.

## Decision

Add the desktop frontend under `interfaces/gui/` as an external adapter. The
entry point is `python -m interfaces.gui.app`.

Keep GUI display state in small mock dataclasses under `interfaces/gui/shared/`.
Widgets consume display models and placeholders only; they do not import DSP,
audio-device, MIDI, or scoring behavior.

Load Monokai themes through a defensive theme registry. JSON theme files are
preferred over HTML templates because they expose richer structured palettes.
If the local theme folders are missing or contain unexpected formats, the GUI
prints a warning and falls back to a built-in Monokai-like palette.

## Alternatives discarded

- Wiring real audio detection during the scaffold was discarded because it
  would mix adapter layout work with capture, detector, and service-boundary
  decisions that are not yet required.
- Wiring MIDI or gameplay into the Player / Hero screen was discarded because
  the current goal is visual structure, not chart timing or scoring behavior.
- Hardcoding a random dark stylesheet was discarded because local Monokai Pro
  assets are an explicit visual requirement and should remain the source for
  theme colors when available.
- Moving GUI code into `audio_detection/` or `minigame/` was discarded because
  PySide6 is a delivery mechanism. The source dependency should point inward to
  use cases later, not make use cases depend on Qt.

## Open decisions

The service boundary between GUI widgets and future audio/gameplay use cases is
intentionally deferred. Device selection, real detector streaming, chart
loading, hit windows, and score updates should be integrated only after their
interfaces are designed explicitly.
