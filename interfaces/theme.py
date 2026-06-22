"""SynthWave 84 color boundary for reachable Qt interfaces.

The source palette was extracted from the provided VS Code SynthWave 84 JSONC
theme. Runtime widgets depend on semantic roles instead of raw token names so
the GUI can change presentation without leaking editor-theme details into
screen code.
"""

from __future__ import annotations

from typing import Final


SYNTHWAVE_THEME_NAME: Final = "SynthWave 84"

SYNTHWAVE_COLORS: Final = frozenset(
    {
        "#03edf9",
        "#09f7a0",
        "#171520",
        "#206d4b",
        "#232530",
        "#241b2f",
        "#262335",
        "#2a2139",
        "#34294f",
        "#36f9f6",
        "#463465",
        "#495495",
        "#614d85",
        "#7059ab",
        "#72f1b8",
        "#848bbd",
        "#a148ab",
        "#b893ce",
        "#d18616",
        "#f3e70f",
        "#f97e72",
        "#fe4450",
        "#fede5d",
        "#ff7edb",
        "#ff8b39",
        "#ffffff",
        "#ffffff99",
        "#ffffffcc",
    }
)

BACKGROUND: Final = "#171520"
TIMELINE_BACKGROUND: Final = "#262335"
PANEL: Final = "#241b2f"
PANEL_ALT: Final = "#2a2139"
PANEL_DEEP: Final = "#232530"
BORDER: Final = "#495495"

TEXT_PRIMARY: Final = "#ffffff"
TEXT_SECONDARY: Final = "#ffffffcc"
TEXT_MUTED: Final = "#ffffff99"
TEXT_DIM: Final = "#848bbd"

ACCENT_PRIMARY: Final = "#ff7edb"
ACCENT_SECONDARY: Final = "#03edf9"
ACCENT_CYAN: Final = "#36f9f6"
ACCENT_CORAL: Final = "#f97e72"

SUCCESS: Final = "#72f1b8"
WARNING: Final = "#fede5d"
ERROR: Final = "#fe4450"
INACTIVE: Final = "#848bbd"

PLAYHEAD: Final = ACCENT_SECONDARY
TIMELINE_NOTE: Final = ACCENT_CYAN
TIMELINE_SELECTED_REGION: Final = ACCENT_PRIMARY
SPECTRUM_BAR: Final = ACCENT_SECONDARY
SPECTRUM_HARMONIC: Final = SUCCESS
SPECTRUM_DOMINANT: Final = ACCENT_CORAL

TRACK_COLORS: Final = (
    ACCENT_SECONDARY,
    ACCENT_PRIMARY,
    SUCCESS,
    WARNING,
    ACCENT_CORAL,
    ACCENT_CYAN,
    "#b893ce",
    "#ff8b39",
)


def qcolor(color: str, alpha: int | None = None):
    """Return a Qt color while preserving VS Code ``#RRGGBBAA`` alpha.

    Qt parses eight-digit hex values as ``#AARRGGBB``. The SynthWave JSONC uses
    VS Code's ``#RRGGBBAA`` convention, so this helper keeps alpha handling in
    one place instead of making every painter remember that adapter mismatch.

    @author Codex - created SynthWave theme color helper.
    """

    from PySide6.QtGui import QColor

    rgb_hex, embedded_alpha = _split_rgb_alpha(color)
    resolved = QColor(rgb_hex)
    if not resolved.isValid():
        raise ValueError(f"Unsupported theme color: {color!r}")
    if alpha is not None:
        resolved.setAlpha(_coerce_alpha(alpha))
    elif embedded_alpha is not None:
        resolved.setAlpha(embedded_alpha)
    return resolved


def css_color(color: str, alpha: int | None = None) -> str:
    """Return a QSS-safe color string from a SynthWave role.

    @author Codex - created SynthWave theme stylesheet helper.
    """

    rgb_hex, embedded_alpha = _split_rgb_alpha(color)
    if alpha is not None:
        return css_rgba(rgb_hex, alpha)
    if embedded_alpha is not None:
        return css_rgba(rgb_hex, embedded_alpha)
    return rgb_hex


def css_rgba(color: str, alpha: int) -> str:
    """Return a Qt stylesheet ``rgba`` color derived from a theme color.

    ``alpha`` uses Qt's 0-255 channel scale. The RGB channels still come from
    the supplied SynthWave color; only opacity is derived for overlays.

    @author Codex - created SynthWave alpha overlay helper.
    """

    parsed = qcolor(color)
    red, green, blue, _alpha = parsed.getRgb()
    return f"rgba({red}, {green}, {blue}, {_coerce_alpha(alpha)})"


def track_swatch_qss(color: str) -> str:
    """Return the reusable style for MIDI track swatches.

    @author Codex - centralized Learn track swatch styling.
    """

    return f"background: {css_color(color)}; border: 1px solid {BORDER}; border-radius: 3px;"


def progress_bar_qss(color: str) -> str:
    """Return the reusable style for semantic Sandbox progress bars.

    @author Codex - centralized Sandbox progress bar styling.
    """

    return f"""
            QProgressBar {{
                background: {PANEL_DEEP};
                border: 1px solid {BORDER};
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background: {css_color(color)};
                border-radius: 5px;
            }}
            """


def screen_base_qss(title_color: str, hover_color: str, *, control_padding: str) -> str:
    """Return shared QSS for reachable operational screens.

    Main Menu has its own presentation, but Learn and Sandbox share the same
    widget vocabulary: panels, inputs, buttons, status labels, and capture
    transport controls.

    @author Codex - centralized reachable screen base styling.
    """

    checked_background = css_rgba(hover_color, 42)
    running_hover = css_rgba(TEXT_PRIMARY, 204)
    return f"""
            QWidget {{
                background: {BACKGROUND};
                color: {TEXT_PRIMARY};
                font-family: Inter, Segoe UI, Arial, sans-serif;
                font-size: 13px;
            }}
            #title {{
                color: {css_color(title_color)};
                font-size: 24px;
                font-weight: 800;
            }}
            #panel {{
                background: {PANEL};
                border: 1px solid {BORDER};
                border-radius: 8px;
            }}
            #sectionTitle {{
                color: {css_color(TEXT_MUTED)};
                font-weight: 800;
            }}
            #status {{
                color: {css_color(TEXT_SECONDARY)};
            }}
            QPushButton, QComboBox, QSpinBox, QTextEdit {{
                background: {PANEL_ALT};
                border: 1px solid {BORDER};
                border-radius: 6px;
                color: {TEXT_PRIMARY};
                padding: {control_padding};
            }}
            QPushButton:hover, QComboBox:hover, QSpinBox:hover {{
                border-color: {css_color(hover_color)};
            }}
            QPushButton:checked {{
                background: {checked_background};
                border-color: {css_color(hover_color)};
            }}
            #inputToggleButton {{
                min-width: 34px;
                max-width: 34px;
                min-height: 34px;
                max-height: 34px;
                border-radius: 17px;
                padding: 0;
                background: {ERROR};
                border: 0;
            }}
            #inputToggleButton:hover {{
                background: {ACCENT_CORAL};
                border: 0;
            }}
            #inputToggleButton[inputState="running"] {{
                border-radius: 4px;
                background: {TEXT_PRIMARY};
                border: 0;
            }}
            #inputToggleButton[inputState="running"]:hover {{
                background: {running_hover};
                border: 0;
            }}
            """


def _split_rgb_alpha(color: str) -> tuple[str, int | None]:
    normalized = color.strip().lower()
    if not normalized.startswith("#"):
        raise ValueError(f"Theme color must be hex: {color!r}")
    if len(normalized) == 7:
        return normalized, None
    if len(normalized) == 9:
        return normalized[:7], int(normalized[7:9], 16)
    raise ValueError(f"Theme color must use #RRGGBB or #RRGGBBAA: {color!r}")


def _coerce_alpha(alpha: int) -> int:
    return max(0, min(255, int(alpha)))
