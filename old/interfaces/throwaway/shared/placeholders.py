"""Generic placeholder widgets for future GUI integrations."""

from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from interfaces.throwaway.shared.cards import Card, muted_label


class PlaceholderCard(Card):
    """Card for a future integration point with visible mocked content.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        title: str,
        lines: list[str],
        parent: QWidget | None = None,
    ):
        super().__init__(title, parent=parent)
        for line in lines:
            self.layout.addWidget(muted_label(line))
        self.layout.addStretch(1)


class LabelList(QWidget):
    """Vertical list of label/value rows for compact placeholder panels.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, rows: list[tuple[str, str]], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        for label, value in rows:
            row = QLabel(f"<b>{label}</b>: {value}")
            row.setWordWrap(True)
            layout.addWidget(row)
