"""Top application bar for the desktop GUI scaffold."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from interfaces.throwaway.shared.models import Theme


class TopBar(QFrame):
    """Static shell header that names the current desktop adapter.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("TopBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        copy = QVBoxLayout()
        copy.setSpacing(2)
        title = QLabel("Guitar Hero Audio Lab")
        title.setObjectName("AppTitle")
        subtitle = QLabel("Desktop scaffold - placeholder UI, no live audio or MIDI wired")
        subtitle.setObjectName("Muted")
        copy.addWidget(title)
        copy.addWidget(subtitle)

        self.theme_label = QLabel()
        self.theme_label.setObjectName("Badge")
        self.set_theme(theme)

        layout.addLayout(copy, 1)
        layout.addWidget(self.theme_label)

    def set_theme(self, theme: Theme) -> None:
        """Update the displayed active theme name.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self.theme_label.setText(f"Theme: {theme.name}")

