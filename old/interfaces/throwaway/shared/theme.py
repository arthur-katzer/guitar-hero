"""Apply normalized Monokai palettes to Qt widgets."""

from __future__ import annotations

from interfaces.throwaway.shared.models import Theme
from interfaces.throwaway.shared.theme_loader import FALLBACK_COLORS


def apply_theme(app_or_widget, theme: Theme) -> None:
    """Apply a Qt stylesheet and pyqtgraph defaults for a theme.

    This function is the single Qt styling boundary so views do not hardcode
    Monokai colors or know where the theme was loaded from.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    app_or_widget.setStyleSheet(build_stylesheet(theme))
    try:
        import pyqtgraph as pg

        colors = _colors(theme)
        pg.setConfigOptions(
            antialias=True,
            background=colors["background"],
            foreground=colors["muted"],
        )
    except Exception:
        return


def build_stylesheet(theme: Theme) -> str:
    """Build the application stylesheet from the normalized palette.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    c = _colors(theme)
    return f"""
QWidget {{
    background: {c["background"]};
    color: {c["text"]};
    font-family: "Segoe UI", "Inter", system-ui, sans-serif;
    font-size: 13px;
}}
QMainWindow, QStackedWidget, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {c["background"]};
}}
QFrame#Card, QFrame#Panel, QFrame#TopBar, QFrame#Navigation, QFrame#StatusBar {{
    background: {c["surface"]};
    border: 1px solid {c["border"]};
    border-radius: 8px;
}}
QLabel#AppTitle {{
    color: {c["text"]};
    font-size: 18px;
    font-weight: 800;
}}
QLabel#SectionTitle {{
    color: {c["text"]};
    font-size: 15px;
    font-weight: 800;
}}
QLabel#CardTitle {{
    color: {c["muted"]};
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 1px;
    text-transform: uppercase;
}}
QLabel#MetricValue {{
    color: {c["accent"]};
    font-size: 30px;
    font-weight: 900;
}}
QLabel#Muted, QLabel#SmallMuted {{
    color: {c["muted"]};
}}
QLabel#SmallMuted {{
    font-size: 11px;
}}
QLabel#Badge {{
    background: {c["surface_alt"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 10px;
    padding: 3px 9px;
    font-weight: 700;
}}
QPushButton {{
    background: {c["button"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 8px 10px;
    font-weight: 700;
}}
QPushButton:hover {{
    background: {c["button_hover"]};
    border-color: {c["accent"]};
}}
QPushButton:checked, QPushButton#NavButton:checked {{
    background: {c["accent"]};
    color: {c["accent_text"]};
    border-color: {c["accent"]};
}}
QPushButton:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
    color: {c["muted"]};
}}
QComboBox, QSpinBox, QDoubleSpinBox {{
    background: {c["input"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    padding: 6px 8px;
}}
QComboBox::drop-down {{
    border: 0;
    width: 22px;
}}
QTableWidget {{
    background: {c["surface"]};
    color: {c["text"]};
    border: 1px solid {c["border"]};
    border-radius: 6px;
    gridline-color: {c["border"]};
    selection-background-color: {c["surface_alt"]};
}}
QHeaderView::section {{
    background: {c["surface_alt"]};
    color: {c["muted"]};
    border: 0;
    border-bottom: 1px solid {c["border"]};
    padding: 6px;
    font-weight: 800;
}}
QSlider::groove:horizontal {{
    height: 6px;
    background: {c["surface_alt"]};
    border-radius: 3px;
}}
QSlider::handle:horizontal {{
    background: {c["accent"]};
    width: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSplitter::handle {{
    background: {c["border"]};
}}
"""


def colors_for(theme: Theme) -> dict[str, str]:
    """Return a complete palette for custom-painted widgets.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    return _colors(theme)


def _colors(theme: Theme) -> dict[str, str]:
    return {**FALLBACK_COLORS, **theme.colors}

