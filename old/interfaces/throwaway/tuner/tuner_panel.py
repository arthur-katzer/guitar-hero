"""Tuner target panel placeholder."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QComboBox, QLabel, QVBoxLayout, QWidget

from interfaces.throwaway.shared.cards import Card, BadgeRow, muted_label
from interfaces.throwaway.shared.models import PitchStatus, STANDARD_TUNING


class TunerPanel(Card):
    """Target-string and tuning-offset placeholder.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, pitch_status: PitchStatus, parent: QWidget | None = None):
        super().__init__("Tuner", "Target string and pitch offset placeholder", parent=parent)

        selector = QComboBox()
        selector.addItems([item.note for item in STANDARD_TUNING])
        selector.setCurrentText(pitch_status.target_note)
        selector.setEnabled(False)

        indicator = QLabel(f"{pitch_status.tuner_cents:+d} cents")
        indicator.setObjectName("MetricValue")
        indicator.setAlignment(Qt.AlignCenter)

        meter = BadgeRow(["FLAT", "IN TUNE", "SHARP"])

        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(8)
        body_layout.addWidget(selector)
        body_layout.addWidget(indicator)
        body_layout.addWidget(meter)
        body_layout.addWidget(muted_label("Needle and cents logic are mocked until audio services are wired."))

        self.layout.addWidget(body)
        self.layout.addStretch(1)

