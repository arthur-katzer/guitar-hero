"""Song selection placeholder panel."""

from __future__ import annotations

from interfaces.throwaway.shared.cards import Card, muted_label
from interfaces.throwaway.shared.controls import LabeledCombo
from interfaces.throwaway.shared.models import GameStatus


class SongSelect(Card):
    """Mock song and difficulty selector.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, game_status: GameStatus, parent=None):
        super().__init__("Song selection", "Future chart picker placeholder", parent=parent)
        self.layout.addWidget(
            LabeledCombo(
                "Song",
                [game_status.song_title, "Mock Blues Scale", "Mock String Crossing"],
                enabled=False,
            )
        )
        self.layout.addWidget(
            LabeledCombo(
                "Difficulty",
                [game_status.difficulty, "Easy", "Hard"],
                enabled=False,
            )
        )
        self.layout.addWidget(muted_label("No MIDI file or chart loader is connected in this scaffold."))
        self.layout.addStretch(1)

