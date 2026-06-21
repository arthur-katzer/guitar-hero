"""Entry point for the current desktop GUI."""

from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from interfaces.debug_dump import dump
from interfaces.gui.main_window import MainWindow


def main(argv: list[str] | None = None) -> int:
    """Run the desktop main menu.

    @author Codex - created the replacement main menu entry point.
    @author Codex - added terminal debug dump lifecycle events.
    """

    dump("app", "start", argv=argv or sys.argv)
    app = QApplication(argv or sys.argv)
    window = MainWindow()
    window.show()
    exit_code = app.exec()
    dump("app", "exit", code=exit_code)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
