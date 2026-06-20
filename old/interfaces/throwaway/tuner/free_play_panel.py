"""Free-play diagnostic cards for tuner mode."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QWidget

from interfaces.throwaway.shared.cards import MetricCard
from interfaces.throwaway.shared.models import AudioStatus, PitchStatus


class FreePlayPanel(QWidget):
    """Mock live-detection summary for the training side of the GUI.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        audio_status: AudioStatus,
        pitch_status: PitchStatus,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QGridLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(12)

        layout.addWidget(
            MetricCard("Live detected note", pitch_status.detected_note, "Mock detector output"),
            0,
            0,
        )
        layout.addWidget(
            MetricCard("Frequency", f"{pitch_status.frequency_hz:.2f} Hz", "Nearest note estimate"),
            0,
            1,
        )
        layout.addWidget(
            MetricCard("RMS / input level", f"{audio_status.rms_level:.2f}", "No real stream connected"),
            1,
            0,
        )
        layout.addWidget(
            MetricCard("Confidence", f"{pitch_status.confidence:.0%}", "Mock confidence score"),
            1,
            1,
        )

