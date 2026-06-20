"""Player / Hero mode screen."""

from __future__ import annotations

from PySide6.QtWidgets import QGridLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from interfaces.throwaway.hero.debug_overlay import DebugOverlay
from interfaces.throwaway.hero.hud import HeroHud
from interfaces.throwaway.hero.lanes import HeroLanes
from interfaces.throwaway.hero.score_panel import ScorePanel
from interfaces.throwaway.hero.song_select import SongSelect
from interfaces.throwaway.shared.models import GameStatus, Theme


class HeroView(QScrollArea):
    """Rhythm-game scaffold screen.

    The view is only a desktop adapter shell. Real gameplay state will come
    from minigame runtime boundaries in a later integration.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        game_status: GameStatus,
        theme: Theme,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self._lanes = HeroLanes(theme)

        content = QWidget()
        layout = QVBoxLayout(content)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("Player / Hero")
        title.setObjectName("SectionTitle")
        layout.addWidget(title)
        layout.addWidget(HeroHud(game_status))

        grid = QGridLayout()
        grid.setSpacing(12)
        grid.addWidget(self._lanes, 0, 0, 3, 2)
        grid.addWidget(SongSelect(game_status), 0, 2)
        grid.addWidget(DebugOverlay(game_status), 1, 2)
        grid.addWidget(ScorePanel(game_status), 3, 0, 1, 3)
        layout.addLayout(grid)
        layout.addStretch(1)

        self.setWidget(content)

    def apply_theme(self, theme: Theme) -> None:
        """Propagate theme changes to custom-painted lanes.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self._lanes.apply_theme(theme)
