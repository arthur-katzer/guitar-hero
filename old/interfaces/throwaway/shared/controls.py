"""Reusable input-looking controls for placeholder settings."""

from __future__ import annotations

from PySide6.QtWidgets import QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QSpinBox, QWidget


class LabeledCombo(QWidget):
    """Label and combo-box pair used in scaffold panels.

    The control can be disabled when it represents future behavior rather than
    a live setting.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        label: str,
        values: list[str],
        *,
        enabled: bool = True,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        caption = QLabel(label)
        caption.setObjectName("Muted")
        self.combo = QComboBox()
        self.combo.addItems(values)
        self.combo.setEnabled(enabled)
        layout.addWidget(caption, 1)
        layout.addWidget(self.combo, 2)


class LabeledSpin(QWidget):
    """Label and numeric spin-box pair for mocked settings.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        label: str,
        value: int,
        *,
        minimum: int = 0,
        maximum: int = 100_000,
        enabled: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        caption = QLabel(label)
        caption.setObjectName("Muted")
        self.spin = QSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setValue(value)
        self.spin.setEnabled(enabled)
        layout.addWidget(caption, 1)
        layout.addWidget(self.spin, 2)


class LabeledFloatSpin(QWidget):
    """Label and decimal spin-box pair for mocked settings.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        label: str,
        value: float,
        *,
        minimum: float = 0.0,
        maximum: float = 1.0,
        enabled: bool = False,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        caption = QLabel(label)
        caption.setObjectName("Muted")
        self.spin = QDoubleSpinBox()
        self.spin.setRange(minimum, maximum)
        self.spin.setSingleStep(0.01)
        self.spin.setValue(value)
        self.spin.setEnabled(enabled)
        layout.addWidget(caption, 1)
        layout.addWidget(self.spin, 2)

