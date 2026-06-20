"""Main window composition for the PySide6 GUI scaffold."""

from __future__ import annotations

from PySide6.QtWidgets import QApplication, QHBoxLayout, QMainWindow, QStackedWidget, QVBoxLayout, QWidget

from interfaces.throwaway.hero.view import HeroView
from interfaces.throwaway.settings.view import SettingsView
from interfaces.throwaway.shared.models import AudioStatus, GameStatus, PitchStatus, Theme
from interfaces.throwaway.shared.theme import apply_theme
from interfaces.throwaway.shared.theme_loader import available_themes, load_theme
from interfaces.throwaway.shell.navigation import Navigation
from interfaces.throwaway.shell.status_bar import StatusBar
from interfaces.throwaway.shell.top_bar import TopBar
from interfaces.throwaway.tuner.view import TunerView


class MainWindow(QMainWindow):
    """Desktop shell for the Guitar Hero GUI scaffold.

    The window composes adapter widgets and mock display models only. Real
    audio, MIDI, and game services remain outside this frontend boundary.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, theme: Theme, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Guitar Hero Audio Lab")
        self.resize(1320, 860)

        self._theme = theme
        self._audio_status = AudioStatus()
        self._pitch_status = PitchStatus()
        self._game_status = GameStatus()

        self.top_bar = TopBar(theme)
        self.navigation = Navigation()
        self.status_bar = StatusBar(self._audio_status, theme)

        theme_names = available_themes()
        self.tuner_view = TunerView(self._audio_status, self._pitch_status, theme)
        self.hero_view = HeroView(self._game_status, theme)
        self.settings_view = SettingsView(
            self._audio_status,
            self._game_status,
            theme_names,
            theme,
        )

        self.stack = QStackedWidget()
        self._mode_indexes = {
            "tuner": self.stack.addWidget(self.tuner_view),
            "hero": self.stack.addWidget(self.hero_view),
            "settings": self.stack.addWidget(self.settings_view),
        }

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)
        root_layout.addWidget(self.top_bar)

        body = QHBoxLayout()
        body.setSpacing(12)
        body.addWidget(self.navigation)
        body.addWidget(self.stack, 1)
        root_layout.addLayout(body, 1)
        root_layout.addWidget(self.status_bar)
        self.setCentralWidget(root)

        self.navigation.mode_selected.connect(self.set_mode)
        self.settings_view.theme_selected.connect(self.set_theme_by_name)
        self.set_mode("tuner")

    def set_mode(self, mode: str) -> None:
        """Switch the central mode area by stable mode key.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        index = self._mode_indexes.get(mode)
        if index is None:
            return
        self.stack.setCurrentIndex(index)
        self.navigation.set_current(mode)

    def set_theme_by_name(self, theme_name: str) -> None:
        """Load and apply a registered theme by name.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self._theme = load_theme(theme_name)
        target = QApplication.instance() or self
        apply_theme(target, self._theme)
        self.top_bar.set_theme(self._theme)
        self.status_bar.set_theme(self._theme)
        self.tuner_view.apply_theme(self._theme)
        self.hero_view.apply_theme(self._theme)
        self.settings_view.set_theme(self._theme)

