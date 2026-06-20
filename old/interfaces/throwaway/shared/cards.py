"""Reusable card widgets for the desktop GUI scaffold."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget


class Card(QFrame):
    """Small framed container used by scaffold panels.

    Cards carry visual grouping only; they do not own business rules or service
    calls.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, title: str, subtitle: str | None = None, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(14, 12, 14, 12)
        self.layout.setSpacing(8)

        header = QVBoxLayout()
        header.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("CardTitle")
        header.addWidget(title_label)
        if subtitle:
            subtitle_label = QLabel(subtitle)
            subtitle_label.setObjectName("SmallMuted")
            subtitle_label.setWordWrap(True)
            header.addWidget(subtitle_label)
        self.layout.addLayout(header)


class MetricCard(Card):
    """Card optimized for one large mocked status value.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        title: str,
        value: str,
        detail: str,
        parent: QWidget | None = None,
    ):
        super().__init__(title, parent=parent)
        self.value_label = QLabel(value)
        self.value_label.setObjectName("MetricValue")
        self.detail_label = QLabel(detail)
        self.detail_label.setObjectName("Muted")
        self.detail_label.setWordWrap(True)
        self.layout.addWidget(self.value_label)
        self.layout.addWidget(self.detail_label)
        self.layout.addStretch(1)


class BadgeRow(QWidget):
    """Horizontal row of compact status badges.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, labels: list[str], parent: QWidget | None = None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        for text in labels:
            badge = QLabel(text)
            badge.setObjectName("Badge")
            badge.setAlignment(Qt.AlignCenter)
            layout.addWidget(badge)
        layout.addStretch(1)


def muted_label(text: str) -> QLabel:
    """Create a muted wrapping label for placeholder explanatory text.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    label = QLabel(text)
    label.setObjectName("Muted")
    label.setWordWrap(True)
    return label

