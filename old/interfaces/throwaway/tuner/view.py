"""Tuner and training mode screen."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from interfaces.throwaway.shared.cards import Card, muted_label
from interfaces.throwaway.shared.models import AudioStatus, PitchStatus, Theme
from interfaces.throwaway.shared.plots import PlotCard
from interfaces.throwaway.tuner.free_play_panel import FreePlayPanel
from interfaces.throwaway.tuner.guitar_reference import GuitarReference
from interfaces.throwaway.tuner.peak_table import PeakTable
from interfaces.throwaway.tuner.target_trainer_panel import TargetTrainerPanel
from interfaces.throwaway.tuner.tuner_panel import TunerPanel


class TunerView(QScrollArea):
    """Diagnostic and practice screen for the desktop scaffold.

    The screen consumes mock display models only. Real detector workflows should
    be connected later through an adapter boundary, not embedded in widgets.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        audio_status: AudioStatus,
        pitch_status: PitchStatus,
        theme: Theme,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._plot_cards: list[PlotCard] = []

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("Tuner / Training")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(FreePlayPanel(audio_status, pitch_status), 0, 0, 1, 2)
        grid.addWidget(TunerPanel(pitch_status), 0, 2)
        grid.addWidget(TargetTrainerPanel(pitch_status), 1, 2)
        grid.addWidget(GuitarReference(), 1, 0)

        warning = Card("Harmonic warning", "Detector explanation placeholder")
        warning.layout.addWidget(muted_label(pitch_status.harmonic_warning))
        warning.layout.addWidget(
            muted_label("Future integration should explain dominant peak versus likely fundamental here.")
        )
        grid.addWidget(warning, 1, 1)

        waveform = PlotCard("Waveform placeholder", kind="waveform", theme=theme)
        spectrum = PlotCard("FFT spectrum placeholder", kind="spectrum", theme=theme)
        chroma = PlotCard("Chroma / pitch-class placeholder", kind="chroma", theme=theme)
        self._plot_cards.extend([waveform, spectrum, chroma])
        grid.addWidget(waveform, 2, 0)
        grid.addWidget(spectrum, 2, 1)
        grid.addWidget(chroma, 2, 2)
        grid.addWidget(PeakTable(), 3, 0, 1, 3)

        layout.addLayout(grid)
        layout.addStretch(1)
        self.setWidget(content)

    def apply_theme(self, theme: Theme) -> None:
        """Propagate theme changes to pyqtgraph placeholders.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        for plot_card in self._plot_cards:
            plot_card.apply_theme(theme)
