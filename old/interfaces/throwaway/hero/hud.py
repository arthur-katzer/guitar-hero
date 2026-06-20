"""Player HUD placeholder panel."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QWidget

from interfaces.throwaway.shared.cards import MetricCard
from interfaces.throwaway.shared.models import GameStatus


class HeroHud(QWidget):
    """Mock current-note HUD for the hero screen.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, game_status: GameStatus, parent: QWidget | None = None):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(MetricCard("Current target note", game_status.current_target_note, "From mock chart"), 0, 0)
        layout.addWidget(MetricCard("Detected note", game_status.detected_note, "Mock input"), 0, 1)
        layout.addWidget(MetricCard("Timing judgment", game_status.judgment, "PERFECT / GOOD / LATE / MISS"), 0, 2)

