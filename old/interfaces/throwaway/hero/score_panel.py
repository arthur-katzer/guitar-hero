"""Score placeholder panel."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QWidget

from interfaces.throwaway.shared.cards import MetricCard
from interfaces.throwaway.shared.models import GameStatus


class ScorePanel(QWidget):
    """Mock scoring summary for the hero mode.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, game_status: GameStatus, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(MetricCard("Score", f"{game_status.score:,}", "Mock score"), 0, 0)
        layout.addWidget(MetricCard("Combo", f"x{game_status.combo}", "Mock streak"), 0, 1)
        layout.addWidget(MetricCard("Accuracy", f"{game_status.accuracy:.1f}%", "Mock hit ratio"), 0, 2)

