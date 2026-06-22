import unittest

from PySide6.QtGui import QColor

from interfaces import theme


class GuiThemeTests(unittest.TestCase):
    def test_semantic_colors_come_from_extracted_synthwave_palette(self):
        roles = (
            theme.BACKGROUND,
            theme.TIMELINE_BACKGROUND,
            theme.PANEL,
            theme.PANEL_ALT,
            theme.PANEL_DEEP,
            theme.BORDER,
            theme.TEXT_PRIMARY,
            theme.TEXT_SECONDARY,
            theme.TEXT_MUTED,
            theme.TEXT_DIM,
            theme.ACCENT_PRIMARY,
            theme.ACCENT_SECONDARY,
            theme.ACCENT_CYAN,
            theme.ACCENT_CORAL,
            theme.SUCCESS,
            theme.WARNING,
            theme.ERROR,
            theme.INACTIVE,
            *theme.TRACK_COLORS,
        )

        for color in roles:
            self.assertIn(color.lower(), theme.SYNTHWAVE_COLORS)

    def test_alpha_helpers_preserve_vscode_hex_alpha_order(self):
        safe_color = theme.qcolor("#ffffff20")
        qt_direct_color = QColor("#ffffff20")

        self.assertEqual(safe_color.getRgb(), (255, 255, 255, 32))
        self.assertNotEqual(qt_direct_color.getRgb(), safe_color.getRgb())
        self.assertEqual(theme.css_color(theme.TEXT_SECONDARY), "rgba(255, 255, 255, 204)")
        self.assertEqual(theme.css_rgba(theme.ACCENT_SECONDARY, 82), "rgba(3, 237, 249, 82)")


if __name__ == "__main__":
    unittest.main()
