"""Throwaway menu highlight prototype gallery."""

from __future__ import annotations

import sys
from dataclasses import dataclass

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QGraphicsDropShadowEffect,
    QGridLayout,
    QLabel,
    QMainWindow,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


MENU_OPTIONS = ("Play", "Training", "Library", "Style")
LANE_COLORS = {
    "Play": "#2ee66b",
    "Training": "#ff4d4d",
    "Library": "#ffd43b",
    "Style": "#339af0",
}


@dataclass(frozen=True)
class HighlightPrototype:
    """Describe a disposable visual treatment for menu selection.

    This prototype exists to compare interaction feel before promoting one
    style into the production main menu.

    @author Codex - created throwaway GUI highlight prototypes.
    """

    name: str
    note: str
    stylesheet: str


PROTOTYPES = (
    HighlightPrototype(
        name="Current",
        note="Subtle background, border, brighter text.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                color: rgba(245, 245, 245, 0.54);
            }
            QPushButton:hover, QPushButton:focus, QPushButton:checked {
                background: rgba(255, 255, 255, 0.10);
                border-color: rgba(255, 255, 255, 0.22);
                color: #ffffff;
            }
        """,
    ),
    HighlightPrototype(
        name="Left Accent",
        note="Strong left rail, restrained body fill.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 0;
                border-left: 4px solid transparent;
                color: rgba(245, 245, 245, 0.50);
                padding-left: 18px;
            }
            QPushButton:hover, QPushButton:focus, QPushButton:checked {
                background: rgba(255, 255, 255, 0.08);
                border-left-color: #2ee66b;
                color: #ffffff;
            }
        """,
    ),
    HighlightPrototype(
        name="Scale",
        note="Bigger selected option with extra weight.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                color: rgba(245, 245, 245, 0.50);
                font-size: 22px;
                padding: 9px 16px;
            }
            QPushButton:hover, QPushButton:focus, QPushButton:checked {
                background: rgba(255, 255, 255, 0.08);
                border-color: rgba(255, 255, 255, 0.18);
                color: #ffffff;
                font-size: 28px;
                font-weight: 800;
                padding: 12px 18px;
            }
        """,
    ),
    HighlightPrototype(
        name="Accent Text",
        note="Flat menu, selected option gets color.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 0;
                color: rgba(245, 245, 245, 0.48);
            }
            QPushButton:hover, QPushButton:focus, QPushButton:checked {
                color: #ffd43b;
            }
        """,
    ),
    HighlightPrototype(
        name="Glow",
        note="White idle text, lane-colored active text and glow.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 0;
                color: #ffffff;
            }
            QPushButton:hover, QPushButton:focus, QPushButton:checked {
                background: transparent;
                border: 0;
            }
        """,
    ),
    HighlightPrototype(
        name="Inverted",
        note="Filled selected item, muted inactive list.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                color: rgba(245, 245, 245, 0.45);
            }
            QPushButton:hover, QPushButton:focus, QPushButton:checked {
                background: #f5f5f5;
                border-color: #f5f5f5;
                color: #111111;
            }
        """,
    ),
    HighlightPrototype(
        name="Lane Colors",
        note="Each option gets a game-lane accent.",
        stylesheet="""
            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                color: rgba(245, 245, 245, 0.50);
            }
            QPushButton[menuOption="Play"]:hover,
            QPushButton[menuOption="Play"]:focus,
            QPushButton[menuOption="Play"]:checked {
                background: rgba(46, 230, 107, 0.16);
                border-color: #2ee66b;
                color: #ffffff;
            }
            QPushButton[menuOption="Training"]:hover,
            QPushButton[menuOption="Training"]:focus,
            QPushButton[menuOption="Training"]:checked {
                background: rgba(255, 77, 77, 0.16);
                border-color: #ff4d4d;
                color: #ffffff;
            }
            QPushButton[menuOption="Library"]:hover,
            QPushButton[menuOption="Library"]:focus,
            QPushButton[menuOption="Library"]:checked {
                background: rgba(255, 212, 59, 0.16);
                border-color: #ffd43b;
                color: #ffffff;
            }
            QPushButton[menuOption="Style"]:hover,
            QPushButton[menuOption="Style"]:focus,
            QPushButton[menuOption="Style"]:checked {
                background: rgba(51, 154, 240, 0.16);
                border-color: #339af0;
                color: #ffffff;
            }
        """,
    ),
)


BASE_PANEL_STYLE = """
    QWidget#prototypePanel {
        background: #181818;
        border: 1px solid #2a2a2a;
        border-radius: 8px;
    }
    QLabel#prototypeTitle {
        color: #f5f5f5;
        font-size: 18px;
        font-weight: 750;
    }
    QLabel#prototypeNote {
        color: rgba(245, 245, 245, 0.62);
        font-size: 12px;
    }
    QPushButton {
        border-radius: 6px;
        font-size: 22px;
        font-weight: 650;
        letter-spacing: 0;
        min-height: 46px;
        padding: 10px 16px;
        text-align: left;
    }
"""


class PrototypePanel(QWidget):
    """Panel showing one menu-highlight option.

    @author Codex - created throwaway GUI highlight prototypes.
    """

    def __init__(self, prototype: HighlightPrototype, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("prototypePanel")
        self.setMinimumWidth(260)
        self.setStyleSheet(BASE_PANEL_STYLE + prototype.stylesheet)

        title = QLabel(prototype.name)
        title.setObjectName("prototypeTitle")
        note = QLabel(prototype.note)
        note.setObjectName("prototypeNote")
        note.setWordWrap(True)

        button_group = QButtonGroup(self)
        button_group.setExclusive(True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)
        layout.addWidget(title)
        layout.addWidget(note)
        layout.addSpacing(12)

        for index, option in enumerate(MENU_OPTIONS):
            button = GlowButton(option, LANE_COLORS[option]) if prototype.name == "Glow" else QPushButton(option)
            button.setProperty("menuOption", option)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button_group.addButton(button, index)
            layout.addWidget(button)
            if index == 0:
                button.setChecked(True)

        layout.addStretch(1)


class GlowButton(QPushButton):
    """Button with lane-colored text and a real graphics-effect glow.

    Qt stylesheets do not support CSS box-shadow, so this throwaway button uses
    ``QGraphicsDropShadowEffect``. The idle state stays visually plain while
    active states combine the user's preferred Accent Text, Lane Colors, and
    Glow directions.

    @author Codex - revised the glow prototype to combine favored styles.
    """

    def __init__(self, text: str, active_color: str, parent: QWidget | None = None):
        super().__init__(text, parent)
        self._active_color = QColor(active_color)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(34)
        self._glow.setOffset(0, 0)
        self._glow.setColor(self._with_alpha(self._active_color, 230))
        self.setGraphicsEffect(self._glow)
        self.toggled.connect(lambda checked: self._sync_glow())
        self._sync_glow()

    def event(self, event: object) -> bool:
        """Refresh glow state for hover and focus transitions.

        @author Codex - revised the glow prototype to combine favored styles.
        """

        handled = super().event(event)
        if hasattr(event, "type") and event.type() in {
            QEvent.Type.Enter,
            QEvent.Type.Leave,
            QEvent.Type.FocusIn,
            QEvent.Type.FocusOut,
        }:
            self._sync_glow()
        return handled

    def _sync_glow(self) -> None:
        """Enable the halo only when the option is active.

        @author Codex - revised the glow prototype to combine favored styles.
        """

        active = self.isChecked() or self.underMouse() or self.hasFocus()
        text_color = self._active_color.name() if active else "#ffffff"
        self.setStyleSheet(f"color: {text_color};")
        self._glow.setEnabled(active)

    def _with_alpha(self, color: QColor, alpha: int) -> QColor:
        """Return a copy of ``color`` with the requested alpha channel.

        @author Codex - revised the glow prototype to combine favored styles.
        """

        copy = QColor(color)
        copy.setAlpha(alpha)
        return copy


class PrototypeWindow(QMainWindow):
    """Host all throwaway highlight options side by side.

    @author Codex - created throwaway GUI highlight prototypes.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Throwaway Menu Highlight Prototypes")
        self.resize(1360, 760)

        content = QWidget()
        content.setObjectName("prototypeRoot")
        grid = QGridLayout(content)
        grid.setContentsMargins(24, 24, 24, 24)
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(18)

        for index, prototype in enumerate(PROTOTYPES):
            row = index // 4
            column = index % 4
            grid.addWidget(PrototypePanel(prototype), row, column)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(content)
        self.setCentralWidget(scroll)
        self.setStyleSheet(
            """
            QMainWindow, QScrollArea, QWidget#prototypeRoot {
                background: #101010;
            }
            QScrollArea {
                border: 0;
            }
            """
        )


def main(argv: list[str] | None = None) -> int:
    """Run the throwaway highlight prototype gallery.

    @author Codex - created throwaway GUI highlight prototypes.
    """

    app = QApplication(argv or sys.argv)
    window = PrototypeWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
