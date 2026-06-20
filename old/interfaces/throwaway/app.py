"""Entry point for the PySide6 desktop GUI scaffold."""

from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path


def prefer_pyside6_qt_libraries() -> None:
    """Prefer PySide6 bundled Qt libraries before importing Qt modules.

    Some Linux environments resolve an incompatible system Qt before the wheel
    libraries. Preloading PySide6's QtCore keeps the scaffold launchable without
    asking developers to manually adjust ``LD_LIBRARY_PATH``.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    if not sys.platform.startswith("linux"):
        return
    try:
        import PySide6

        qt_lib_dir = Path(PySide6.__file__).resolve().parent / "Qt" / "lib"
        qt_core = qt_lib_dir / "libQt6Core.so.6"
        if qt_core.exists():
            existing = os.environ.get("LD_LIBRARY_PATH")
            os.environ["LD_LIBRARY_PATH"] = f"{qt_lib_dir}:{existing}" if existing else str(qt_lib_dir)
            ctypes.CDLL(str(qt_core), mode=ctypes.RTLD_GLOBAL)
    except Exception as exc:
        print(f"[gui] Could not preload PySide6 Qt libraries: {exc}", file=sys.stderr)


prefer_pyside6_qt_libraries()

from PySide6.QtWidgets import QApplication

from interfaces.throwaway.main_window import MainWindow
from interfaces.throwaway.shared.theme import apply_theme
from interfaces.throwaway.shared.theme_loader import DEFAULT_THEME_NAME, load_theme


def main(argv: list[str] | None = None) -> int:
    """Run the desktop GUI scaffold.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    app = QApplication(argv or sys.argv)
    theme = load_theme(DEFAULT_THEME_NAME)
    apply_theme(app, theme)
    window = MainWindow(theme)
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

