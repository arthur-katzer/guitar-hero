"""Standard guitar tuning reference panel."""

from __future__ import annotations

from interfaces.throwaway.shared.cards import Card
from interfaces.throwaway.shared.models import STANDARD_TUNING
from interfaces.throwaway.shared.placeholders import LabelList


class GuitarReference(Card):
    """Display standard guitar tuning notes and frequencies.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, parent=None):
        super().__init__("Guitar standard tuning", "Reference frequencies used by the mock layout", parent=parent)
        self.layout.addWidget(
            LabelList([(item.note, f"{item.frequency_hz:.2f} Hz") for item in STANDARD_TUNING])
        )
        self.layout.addStretch(1)

