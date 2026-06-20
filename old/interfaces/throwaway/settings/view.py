"""Settings screen for the desktop GUI scaffold."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from interfaces.throwaway.settings.audio_settings import AudioSettings
from interfaces.throwaway.settings.gameplay_settings import GameplaySettings
from interfaces.throwaway.settings.theme_settings import ThemeSettings
from interfaces.throwaway.shared.models import AudioStatus, GameStatus, Theme


class SettingsView(QScrollArea):
    """Placeholder settings screen with a functional theme selector.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    theme_selected = Signal(str)

    def __init__(
        self,
        audio_status: AudioStatus,
        game_status: GameStatus,
        theme_names: list[str],
        active_theme: Theme,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWidgetResizable(True)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("Settings")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)

        self.theme_settings = ThemeSettings(theme_names, active_theme)
        self.theme_settings.theme_selected.connect(self.theme_selected.emit)

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(AudioSettings(audio_status), 0, 0)
        grid.addWidget(GameplaySettings(game_status), 0, 1)
        grid.addWidget(self.theme_settings, 1, 0, 1, 2)
        layout.addLayout(grid)
        layout.addStretch(1)
        self.setWidget(content)

    def set_theme(self, theme: Theme) -> None:
        """Update theme-specific settings preview.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self.theme_settings.set_theme(theme)
