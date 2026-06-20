"""Mode navigation for the desktop GUI scaffold."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QButtonGroup, QFrame, QPushButton, QVBoxLayout, QWidget


class Navigation(QFrame):
    """Left-side mode selector for the GUI adapter.

    The navigation emits mode keys only; it does not know how screens are built
    or how future use cases will be wired.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    mode_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("Navigation")
        self.setMinimumWidth(180)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in (
            ("tuner", "Tuner / Training"),
            ("hero", "Player / Hero"),
            ("settings", "Settings"),
        ):
            button = QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.clicked.connect(lambda checked=False, mode=key: self.mode_selected.emit(mode))
            self._group.addButton(button)
            self._buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        self.set_current("tuner")

    def set_current(self, mode: str) -> None:
        """Mark a mode as selected without rebuilding navigation.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        button = self._buttons.get(mode)
        if button:
            button.setChecked(True)

