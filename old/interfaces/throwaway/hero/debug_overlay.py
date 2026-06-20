"""Compact debug overlay placeholder."""

from __future__ import annotations

from interfaces.throwaway.shared.cards import Card
from interfaces.throwaway.shared.models import GameStatus
from interfaces.throwaway.shared.placeholders import LabelList


class DebugOverlay(Card):
    """Mock detector/debug facts for the hero screen.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, game_status: GameStatus, parent=None):
        super().__init__("Debug overlay", "Compact input diagnostics placeholder", parent=parent)
        self.layout.addWidget(
            LabelList(
                [
                    ("RMS", f"{game_status.rms:.2f}"),
                    ("Detected note", game_status.detected_note),
                    ("Confidence", f"{game_status.confidence:.0%}"),
                    ("Pitch mode", game_status.pitch_mode),
                ]
            )
        )
        self.layout.addStretch(1)

