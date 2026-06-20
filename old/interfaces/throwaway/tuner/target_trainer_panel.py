"""Target trainer placeholder panel."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from interfaces.throwaway.shared.cards import Card, BadgeRow, muted_label
from interfaces.throwaway.shared.models import PitchStatus
from interfaces.throwaway.shared.placeholders import LabelList


class TargetTrainerPanel(Card):
    """Mock target-note trainer status.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, pitch_status: PitchStatus, parent=None):
        super().__init__("Target trainer", "Practice target feedback placeholder", parent=parent)

        self.layout.addWidget(
            LabelList(
                [
                    ("Target note", pitch_status.target_note),
                    ("Detected note", pitch_status.detected_note),
                ]
            )
        )
        state = QLabel(pitch_status.trainer_state)
        state.setObjectName("MetricValue")
        state.setAlignment(Qt.AlignCenter)
        self.layout.addWidget(state)
        self.layout.addWidget(BadgeRow(["HIT", "MISS", "WAITING"]))
        self.layout.addWidget(muted_label("Hold timers and target rotation are not connected yet."))
        self.layout.addStretch(1)

