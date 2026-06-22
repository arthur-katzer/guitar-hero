# ADR 0010: SynthWave 84 Theme Boundary

## Status

Accepted.

## Context

The app is being repainted from a VS Code SynthWave 84 JSONC file. That file is
an external input from a developer machine, includes JSONC syntax such as a
trailing comma, and uses editor-token color names that are not product UI
roles.

Qt also parses eight-digit hex colors as `#AARRGGBB`, while VS Code theme files
use `#RRGGBBAA`. Passing values such as `#ffffff20` directly to Qt would produce
the wrong RGB color instead of a white overlay with low opacity.

## Decision

The extracted palette is checked into `interfaces/theme.py` as semantic roles.
Runtime GUI code imports those roles and helper functions instead of reading the
file from `Downloads` or scattering raw hex values across widgets.

Alpha overlays are derived through `qcolor`, `css_color`, and `css_rgba`. The
helpers treat the source palette as VS Code `#RRGGBBAA` and output Qt-safe
`QColor` objects or QSS `rgba(...)` values.

## Alternatives Discarded

- Runtime loading from `/home/katzer/Downloads/synthwave-color-theme.json` was
  discarded because the app would depend on a developer-local file path.
- Copying the raw JSONC into the product and parsing it at runtime was
  discarded because editor-token names are not stable product UI roles.
- Passing eight-digit hex values directly into Qt was discarded because Qt and
  VS Code use different byte ordering for alpha.

## Open Decisions

Play remains outside this repaint because it is currently hidden from the main
menu. If Play is re-enabled, it should consume the same theme module rather than
reviving its old hardcoded palette.
