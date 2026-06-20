"""Entry point for the current desktop GUI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from interfaces.gui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    """Run the desktop main menu.

    @author Codex - created the replacement main menu entry point.
    """

    app = QApplication(argv or sys.argv)
    window = MainWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
