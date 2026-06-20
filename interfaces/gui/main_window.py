"""Main menu window for the current desktop GUI."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)


MAIN_MENU_OPTIONS = ("Play", "Training", "Library", "Style")


class MainMenu(QWidget):
    """Expose the game's top-level navigation choices.

    The menu is intentionally only a navigation boundary for now: each option
    emits a stable screen name, while the destination screens remain deferred
    until their use cases are defined.

    @author Codex - created the replacement main menu interface.
    """

    option_selected = Signal(str)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("mainMenu")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self._buttons: list[QPushButton] = []
        self._button_group = QButtonGroup(self)
        self._button_group.setExclusive(True)

        menu_layout = QVBoxLayout()
        menu_layout.setContentsMargins(0, 0, 0, 0)
        menu_layout.setSpacing(14)
        menu_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)

        for index, label in enumerate(MAIN_MENU_OPTIONS):
            button = QPushButton(label)
            button.setCheckable(True)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setMinimumHeight(48)
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.clicked.connect(lambda checked=False, value=label: self.option_selected.emit(value))
            button.installEventFilter(self)
            self._button_group.addButton(button, index)
            self._buttons.append(button)
            menu_layout.addWidget(button)

        container = QWidget()
        container.setObjectName("mainMenuOptions")
        container.setMaximumWidth(360)
        container.setLayout(menu_layout)

        root_layout = QVBoxLayout(self)
        root_layout.setContentsMargins(32, 24, 32, 24)
        root_layout.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        root_layout.addWidget(container)

        self.set_current_index(0)

    @property
    def buttons(self) -> tuple[QPushButton, ...]:
        """Return the selectable menu controls for tests and shell integration.

        @author Codex - created the replacement main menu interface.
        """

        return tuple(self._buttons)

    def eventFilter(self, watched: object, event: object) -> bool:
        """Keep mouse hover and keyboard focus visually aligned.

        Hovered or focused options become the current choice so mouse and arrow
        navigation share one selection state instead of competing styles.

        @author Codex - created the replacement main menu interface.
        """

        if watched in self._buttons and hasattr(event, "type"):
            event_type = event.type()
            if event_type in {
                QEvent.Type.Enter,
                QEvent.Type.FocusIn,
            }:
                self.set_current_index(self._buttons.index(watched))
        return super().eventFilter(watched, event)

    def keyPressEvent(self, event: object) -> None:
        """Move selection with arrow keys and activate it with Enter or Space.

        @author Codex - created the replacement main menu interface.
        """

        key = event.key()
        current_index = self.current_index()
        if key in {Qt.Key.Key_Down, Qt.Key.Key_Right}:
            self.set_current_index((current_index + 1) % len(self._buttons))
            return
        if key in {Qt.Key.Key_Up, Qt.Key.Key_Left}:
            self.set_current_index((current_index - 1) % len(self._buttons))
            return
        if key in {Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space}:
            self._buttons[current_index].click()
            return
        super().keyPressEvent(event)

    def current_index(self) -> int:
        """Return the currently highlighted option index.

        @author Codex - created the replacement main menu interface.
        """

        checked_id = self._button_group.checkedId()
        return checked_id if checked_id >= 0 else 0

    def set_current_index(self, index: int) -> None:
        """Highlight a valid menu option by index.

        @author Codex - created the replacement main menu interface.
        """

        if not 0 <= index < len(self._buttons):
            return
        button = self._buttons[index]
        button.setChecked(True)
        button.setFocus(Qt.FocusReason.OtherFocusReason)


class MainWindow(QMainWindow):
    """Host the current GUI entry screen.

    @author Codex - created the replacement main menu interface.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Guitar Hero")
        self.resize(960, 640)
        self.menu = MainMenu()
        self.setCentralWidget(self.menu)
        self.setStyleSheet(
            """
            QMainWindow, QWidget#mainMenu {
                background: #111111;
                color: #f5f5f5;
            }

            QWidget#mainMenuOptions {
                background: transparent;
            }

            QPushButton {
                background: transparent;
                border: 1px solid transparent;
                border-radius: 6px;
                color: rgba(245, 245, 245, 0.54);
                font-size: 24px;
                font-weight: 650;
                letter-spacing: 0;
                padding: 10px 18px;
                text-align: left;
            }

            QPushButton:hover,
            QPushButton:focus,
            QPushButton:checked {
                background: rgba(255, 255, 255, 0.10);
                border-color: rgba(255, 255, 255, 0.22);
                color: #ffffff;
            }

            QPushButton:pressed {
                background: rgba(255, 255, 255, 0.16);
            }
            """
        )
