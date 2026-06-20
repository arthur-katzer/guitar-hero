"""Gameplay settings placeholder panel."""

from __future__ import annotations

from interfaces.throwaway.shared.cards import Card, muted_label
from interfaces.throwaway.shared.controls import LabeledCombo, LabeledSpin
from interfaces.throwaway.shared.models import GameStatus


class GameplaySettings(Card):
    """Mock gameplay settings for future runtime integration.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, game_status: GameStatus, parent=None):
        super().__init__("Gameplay settings", "Future hit-window and display configuration", parent=parent)
        self.layout.addWidget(LabeledSpin("Timing window", 90, maximum=500, enabled=False))
        self.layout.addWidget(
            LabeledCombo("Difficulty", [game_status.difficulty, "Easy", "Hard"], enabled=False)
        )
        self.layout.addWidget(
            LabeledCombo("Note display mode", ["Scientific pitch", "String names", "Lane colors"], enabled=False)
        )
        self.layout.addWidget(muted_label("No scoring or minigame runtime settings are connected yet."))
        self.layout.addStretch(1)

