"""Guitar Hero-style lane placeholder."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QFrame, QWidget

from interfaces.throwaway.shared.models import Theme
from interfaces.throwaway.shared.theme import colors_for


class HeroLanes(QFrame):
    """Static lane renderer for the future rhythm-game screen.

    The widget draws visible lanes and falling-note placeholders without
    depending on chart timing, MIDI playback, or scoring services.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setMinimumHeight(380)
        self._theme = theme

    def apply_theme(self, theme: Theme) -> None:
        """Refresh custom-painted colors for the active theme.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self._theme = theme
        self.update()

    def paintEvent(self, event) -> None:
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        c = colors_for(self._theme)
        rect = self.rect().adjusted(18, 18, -18, -18)
        painter.fillRect(rect, QColor(c["surface"]))

        lane_colors = [c["green"], c["red"], c["yellow"], c["cyan"], c["purple"], c["orange"]]
        lane_count = len(lane_colors)
        lane_width = rect.width() / lane_count
        hit_y = rect.bottom() - 52

        painter.setPen(QPen(QColor(c["border"]), 2))
        for lane_index in range(lane_count + 1):
            x = rect.left() + lane_index * lane_width
            painter.drawLine(int(x), rect.top(), int(x), rect.bottom())

        painter.setPen(QPen(QColor(c["accent"]), 4))
        painter.drawLine(rect.left(), int(hit_y), rect.right(), int(hit_y))

        notes = [
            (0, 0.72),
            (1, 0.44),
            (2, 0.21),
            (3, 0.62),
            (4, 0.34),
            (5, 0.12),
            (2, 0.82),
        ]
        for lane_index, y_ratio in notes:
            center_x = rect.left() + lane_width * (lane_index + 0.5)
            center_y = rect.top() + rect.height() * y_ratio
            note_rect = QRectF(center_x - 22, center_y - 14, 44, 28)
            painter.setBrush(QColor(lane_colors[lane_index]))
            painter.setPen(QPen(QColor(c["border"]), 1))
            painter.drawRoundedRect(note_rect, 12, 12)

        painter.setPen(QPen(QColor(c["muted"]), 1))
        painter.drawText(QPointF(rect.left(), rect.top() - 4), "Falling note lane placeholder")
        painter.setPen(QPen(QColor(c["accent"]), 1))
        painter.drawText(QPointF(rect.left(), hit_y - 8), "Hit line")
        painter.end()

