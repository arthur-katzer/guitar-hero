"""Theme settings panel."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from interfaces.throwaway.shared.cards import Card, muted_label
from interfaces.throwaway.shared.controls import LabeledCombo
from interfaces.throwaway.shared.models import Theme
from interfaces.throwaway.shared.theme import colors_for


class ThemeSettings(Card):
    """Theme selector backed by the Monokai registry.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    theme_selected = Signal(str)

    def __init__(self, theme_names: list[str], active_theme: Theme, parent=None):
        super().__init__("Theme settings", "Loaded from local Monokai assets when available", parent=parent)
        self.selector = LabeledCombo("Monokai theme", theme_names or [active_theme.name], enabled=True)
        self.selector.combo.setCurrentText(active_theme.name)
        self.selector.combo.currentTextChanged.connect(self.theme_selected.emit)
        self.layout.addWidget(self.selector)
        self.swatches = QWidget()
        self.swatch_layout = QHBoxLayout(self.swatches)
        self.swatch_layout.setContentsMargins(0, 0, 0, 0)
        self.swatch_layout.setSpacing(8)
        self.layout.addWidget(self.swatches)
        self.layout.addWidget(muted_label("Theme switching updates Qt stylesheets and custom plot colors."))
        self.layout.addStretch(1)
        self.set_theme(active_theme)

    def set_theme(self, theme: Theme) -> None:
        """Update preview swatches for the active theme.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self.selector.combo.blockSignals(True)
        self.selector.combo.setCurrentText(theme.name)
        self.selector.combo.blockSignals(False)

        while self.swatch_layout.count():
            item = self.swatch_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        colors = colors_for(theme)
        for name in ("background", "surface", "accent", "cyan", "green", "red", "purple"):
            swatch = QLabel(name)
            swatch.setObjectName("Badge")
            swatch.setStyleSheet(
                f"background: {colors[name]}; color: {colors['text']}; border: 1px solid {colors['border']};"
            )
            self.swatch_layout.addWidget(swatch)
        self.swatch_layout.addStretch(1)

