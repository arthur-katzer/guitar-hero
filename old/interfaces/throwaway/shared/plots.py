"""PyQtGraph placeholders used by the desktop scaffold."""

from __future__ import annotations

import math

import pyqtgraph as pg
from PySide6.QtWidgets import QWidget

from interfaces.throwaway.shared.cards import Card
from interfaces.throwaway.shared.models import Theme
from interfaces.throwaway.shared.theme import colors_for


class PlotCard(Card):
    """Card containing a themed static pyqtgraph placeholder.

    The plot data is deterministic mock data so the GUI can validate layout
    without starting audio capture or analysis.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        title: str,
        *,
        kind: str,
        theme: Theme,
        parent: QWidget | None = None,
    ):
        super().__init__(title, parent=parent)
        self.kind = kind
        self.plot = pg.PlotWidget()
        self.plot.setMinimumHeight(180)
        self.plot.showGrid(x=True, y=True, alpha=0.18)
        self.layout.addWidget(self.plot)
        self.apply_theme(theme)
        self._draw_placeholder(theme)

    def apply_theme(self, theme: Theme) -> None:
        """Apply non-QSS plot colors after a theme switch.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        c = colors_for(theme)
        self.plot.setBackground(c["surface"])
        self.plot.getAxis("bottom").setPen(c["muted"])
        self.plot.getAxis("left").setPen(c["muted"])
        self.plot.getAxis("bottom").setTextPen(c["muted"])
        self.plot.getAxis("left").setTextPen(c["muted"])
        self._draw_placeholder(theme)

    def _draw_placeholder(self, theme: Theme) -> None:
        c = colors_for(theme)
        self.plot.clear()
        if self.kind == "waveform":
            x_values = [index / 50 for index in range(240)]
            y_values = [
                math.sin(index / 9) * 0.55 + math.sin(index / 3.7) * 0.08
                for index in range(240)
            ]
            self.plot.plot(x_values, y_values, pen=pg.mkPen(c["cyan"], width=2))
            self.plot.setLabel("bottom", "time", units="s")
            self.plot.setLabel("left", "amplitude")
            return

        if self.kind == "spectrum":
            x_values = [40 + index * 14 for index in range(90)]
            y_values = [
                max(0.02, math.exp(-((frequency - 220) / 90) ** 2))
                + max(0.02, 0.55 * math.exp(-((frequency - 440) / 80) ** 2))
                for frequency in x_values
            ]
            self.plot.plot(x_values, y_values, pen=pg.mkPen(c["green"], width=2))
            self.plot.setLabel("bottom", "frequency", units="Hz")
            self.plot.setLabel("left", "magnitude")
            return

        labels = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
        values = [0.12, 0.18, 0.28, 0.12, 0.85, 0.36, 0.21, 0.55, 0.18, 0.96, 0.2, 0.42]
        bars = pg.BarGraphItem(
            x=list(range(len(values))),
            height=values,
            width=0.72,
            brush=pg.mkBrush(c["purple"]),
            pen=pg.mkPen(c["border"]),
        )
        self.plot.addItem(bars)
        self.plot.getAxis("bottom").setTicks([list(enumerate(labels))])
        self.plot.setLabel("bottom", "pitch class")
        self.plot.setLabel("left", "energy")

