import unittest
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEvent, Qt
from PySide6.QtWidgets import QApplication

from interfaces.gui.main_window import MAIN_MENU_OPTIONS, MainMenu


class GuiMainMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_exposes_expected_options_in_order(self):
        menu = MainMenu()

        self.assertEqual([button.text() for button in menu.buttons], list(MAIN_MENU_OPTIONS))

    def test_arrow_keys_change_highlighted_option(self):
        menu = MainMenu()

        self.assertEqual(menu.current_index(), 0)

        self._press(menu, Qt.Key.Key_Down)
        self.assertEqual(menu.current_index(), 1)

        self._press(menu, Qt.Key.Key_Up)
        self.assertEqual(menu.current_index(), 0)

    def test_enter_activates_current_option(self):
        menu = MainMenu()
        selected = []
        menu.option_selected.connect(selected.append)

        self._press(menu, Qt.Key.Key_Down)
        self._press(menu, Qt.Key.Key_Return)

        self.assertEqual(selected, ["Training"])

    def test_hover_changes_highlighted_option(self):
        menu = MainMenu()

        menu.eventFilter(menu.buttons[2], QEvent(QEvent.Type.Enter))

        self.assertEqual(menu.current_index(), 2)

    def _press(self, menu: MainMenu, key: Qt.Key) -> None:
        event = _KeyEvent(key)
        menu.keyPressEvent(event)


class _KeyEvent:
    def __init__(self, key: Qt.Key):
        self._key = key

    def key(self):
        return self._key


if __name__ == "__main__":
    unittest.main()
