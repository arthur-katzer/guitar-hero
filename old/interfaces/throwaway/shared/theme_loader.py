"""Load Monokai themes for the PySide6 GUI scaffold.

The loader is intentionally defensive because these local theme folders are
developer assets, not application-owned runtime dependencies.
"""

from __future__ import annotations

import json
import re
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from interfaces.throwaway.shared.models import Theme


DEFAULT_THEME_NAME = "Monokai Pro"
THEME_DIRS: tuple[Path, ...] = (
    Path("/home/katzer/dev/bin/frontend-templates"),
    Path("/home/katzer/dev/bin/monokai-frontends"),
    Path("/home/katzer/dev/bin/monokai-themes"),
)

FALLBACK_COLORS: dict[str, str] = {
    "background": "#2d2a2e",
    "surface": "#221f22",
    "surface_alt": "#403e41",
    "text": "#fcfcfa",
    "muted": "#939293",
    "border": "#19181a",
    "accent": "#ffd866",
    "accent_text": "#2d2a2e",
    "cyan": "#78dce8",
    "green": "#a9dc76",
    "orange": "#fc9867",
    "red": "#ff6188",
    "yellow": "#ffd866",
    "purple": "#ab9df2",
    "button": "#403e41",
    "button_hover": "#5b595c",
    "input": "#2d2a2e",
}

_CSS_VAR_RE = re.compile(
    r"--(?P<name>[a-zA-Z0-9_-]+)\s*:\s*(?P<value>#[0-9a-fA-F]{3,8}|rgba?\([^)]+\))"
)
_TITLE_RE = re.compile(r"<title>(?P<title>.*?)</title>", re.IGNORECASE | re.DOTALL)


def available_themes(source_dirs: Iterable[str | Path] | None = None) -> list[str]:
    """Return the registered Monokai theme names.

    The optional ``source_dirs`` hook keeps discovery testable without binding
    tests to the developer's machine paths.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    return sorted(_discover_themes(source_dirs).keys(), key=str.casefold)


def load_theme(
    name: str | None = None, source_dirs: Iterable[str | Path] | None = None
) -> Theme:
    """Load a normalized theme by name, falling back to Monokai Pro.

    Missing folders and malformed theme files should not prevent the GUI shell
    from opening; the scaffold can still run with the built-in palette.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    registry = _discover_themes(source_dirs)
    if not registry:
        _warn("No Monokai themes could be loaded; using built-in fallback palette.")
        return _fallback_theme()

    requested_name = name or DEFAULT_THEME_NAME
    if requested_name in registry:
        return registry[requested_name]

    if DEFAULT_THEME_NAME in registry:
        _warn(f"Theme '{requested_name}' was not found; using '{DEFAULT_THEME_NAME}'.")
        return registry[DEFAULT_THEME_NAME]

    first_name = sorted(registry, key=str.casefold)[0]
    _warn(f"Theme '{requested_name}' was not found; using '{first_name}'.")
    return registry[first_name]


def _discover_themes(source_dirs: Iterable[str | Path] | None = None) -> dict[str, Theme]:
    dirs = tuple(Path(path) for path in (source_dirs or THEME_DIRS))
    registry: dict[str, Theme] = {}

    for path in _iter_theme_files(dirs, suffix=".json"):
        theme = _load_json_theme(path)
        if theme and theme.name not in registry:
            registry[theme.name] = theme

    for path in _iter_theme_files(dirs, suffix=".html"):
        theme = _load_html_theme(path)
        if theme and theme.name not in registry:
            registry[theme.name] = theme

    return registry


def _iter_theme_files(source_dirs: tuple[Path, ...], *, suffix: str) -> Iterable[Path]:
    for directory in source_dirs:
        if not directory.exists():
            _warn(f"Theme directory is unavailable: {directory}")
            continue
        if not directory.is_dir():
            _warn(f"Theme path is not a directory: {directory}")
            continue
        yield from sorted(directory.glob(f"*{suffix}"), key=lambda path: path.name.casefold())


def _load_json_theme(path: Path) -> Theme | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        _warn(f"Could not parse theme JSON '{path}': {exc}")
        return None

    raw_colors = data.get("colors")
    if not isinstance(raw_colors, dict):
        _warn(f"Theme JSON '{path}' does not contain a colors object.")
        return None

    name = str(data.get("name") or path.stem)
    kind = _theme_kind(data.get("type"))
    colors = _normalize_vscode_palette(raw_colors, kind=kind)
    return Theme(name=name, kind=kind, colors=colors, source=str(path))


def _load_html_theme(path: Path) -> Theme | None:
    if not path.stem.casefold().startswith("monokai-"):
        return None

    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        _warn(f"Could not read theme HTML '{path}': {exc}")
        return None

    variables = dict(_CSS_VAR_RE.findall(text))
    if not variables:
        return None

    name = _html_theme_name(path, text)
    if name.casefold() == "monokai":
        return None
    kind = "light" if "light" in name.casefold() else "dark"
    colors = _normalize_html_palette(variables, kind=kind)
    return Theme(name=name, kind=kind, colors=colors, source=str(path))


def _normalize_vscode_palette(raw: dict[str, Any], *, kind: str) -> dict[str, str]:
    fallback = _fallback_palette(kind)

    def pick(*keys: str, default: str) -> str:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, str) and value:
                return value
        return default

    return {
        "background": pick("editor.background", "window.background", default=fallback["background"]),
        "surface": pick(
            "sideBar.background",
            "activityBarTop.background",
            "editorGroupHeader.tabsBackground",
            default=fallback["surface"],
        ),
        "surface_alt": pick("panel.background", "button.background", default=fallback["surface_alt"]),
        "text": pick("foreground", "editor.foreground", default=fallback["text"]),
        "muted": pick("descriptionForeground", "sideBar.foreground", default=fallback["muted"]),
        "border": pick("panel.border", "activityBar.border", "editorGroup.border", default=fallback["border"]),
        "accent": pick(
            "activityBarBadge.background",
            "panelTitle.activeBorder",
            "charts.yellow",
            "checkbox.foreground",
            default=fallback["accent"],
        ),
        "accent_text": pick(
            "activityBarBadge.foreground",
            "badge.foreground",
            default=fallback["accent_text"],
        ),
        "cyan": pick("charts.blue", "editorInfo.foreground", default=fallback["cyan"]),
        "green": pick("charts.green", default=fallback["green"]),
        "orange": pick("charts.orange", default=fallback["orange"]),
        "red": pick("charts.red", "errorForeground", default=fallback["red"]),
        "yellow": pick("charts.yellow", default=fallback["yellow"]),
        "purple": pick("charts.purple", default=fallback["purple"]),
        "button": pick("button.background", default=fallback["button"]),
        "button_hover": pick("button.hoverBackground", default=fallback["button_hover"]),
        "input": pick("input.background", "dropdown.background", default=fallback["input"]),
    }


def _normalize_html_palette(raw: dict[str, str], *, kind: str) -> dict[str, str]:
    fallback = _fallback_palette(kind)

    def pick(*keys: str, default: str) -> str:
        for key in keys:
            value = raw.get(key)
            if isinstance(value, str) and value:
                return value
        return default

    return {
        "background": pick("bg", default=fallback["background"]),
        "surface": pick("panel", default=fallback["surface"]),
        "surface_alt": pick("panel-soft", "button-bg", default=fallback["surface_alt"]),
        "text": pick("ink", default=fallback["text"]),
        "muted": pick("muted", default=fallback["muted"]),
        "border": pick("line", default=fallback["border"]),
        "accent": pick("yellow", "cyan", default=fallback["accent"]),
        "accent_text": fallback["accent_text"],
        "cyan": pick("cyan", default=fallback["cyan"]),
        "green": pick("lime", "green", default=fallback["green"]),
        "orange": pick("orange", default=fallback["orange"]),
        "red": pick("red", default=fallback["red"]),
        "yellow": pick("yellow", default=fallback["yellow"]),
        "purple": pick("purple", default=fallback["purple"]),
        "button": pick("button-bg", default=fallback["button"]),
        "button_hover": pick("panel-soft", default=fallback["button_hover"]),
        "input": pick("input-bg", default=fallback["input"]),
    }


def _html_theme_name(path: Path, text: str) -> str:
    match = _TITLE_RE.search(text)
    if match:
        title = " ".join(match.group("title").split())
        monokai_at = title.casefold().find("monokai")
        if monokai_at >= 0:
            return _normalize_theme_name(title[monokai_at:])
    return _normalize_theme_name(path.stem)


def _normalize_theme_name(value: str) -> str:
    simplified = value.strip().replace("_", "-")
    lower = simplified.casefold()
    if lower.startswith("monokai-pro-light-filter-"):
        suffix = simplified.split("filter-", 1)[1].replace("-", " ").title()
        return f"Monokai Pro Light (Filter {suffix})"
    if lower.startswith("monokai-pro-filter-"):
        suffix = simplified.split("filter-", 1)[1].replace("-", " ").title()
        return f"Monokai Pro (Filter {suffix})"
    if lower == "monokai-pro-light":
        return "Monokai Pro Light"
    if lower == "monokai-pro":
        return "Monokai Pro"
    if lower == "monokai-classic":
        return "Monokai Classic"
    return value.strip()


def _theme_kind(value: object) -> str:
    return "light" if str(value).casefold() == "light" else "dark"


def _fallback_theme() -> Theme:
    return Theme(
        name=DEFAULT_THEME_NAME,
        kind="dark",
        colors=_fallback_palette("dark"),
        source="built-in fallback",
    )


def _fallback_palette(kind: str) -> dict[str, str]:
    if kind == "light":
        return {
            **FALLBACK_COLORS,
            "background": "#faf4f2",
            "surface": "#ede7e5",
            "surface_alt": "#e0dad9",
            "text": "#29242a",
            "muted": "#706b6e",
            "border": "#d3cdcc",
            "accent": "#e14775",
            "accent_text": "#faf4f2",
            "button": "#e0dad9",
            "button_hover": "#d3cdcc",
            "input": "#fefaf9",
            "cyan": "#1c8ca8",
            "green": "#269d69",
            "orange": "#e16032",
            "red": "#e14775",
            "yellow": "#cc7a0a",
            "purple": "#7058be",
        }
    return dict(FALLBACK_COLORS)


def _warn(message: str) -> None:
    print(f"[gui theme] {message}", file=sys.stderr)
