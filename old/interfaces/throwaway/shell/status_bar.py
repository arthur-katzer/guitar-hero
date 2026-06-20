"""Bottom status strip for the desktop GUI scaffold."""

from __future__ import annotations

from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QWidget

from interfaces.throwaway.shared.models import AudioStatus, Theme


class StatusBar(QFrame):
    """Compact status strip for mocked adapter state.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(
        self,
        audio_status: AudioStatus,
        theme: Theme,
        parent: QWidget | None = None,
    ):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 12, 8)
        layout.setSpacing(14)

        self.audio_label = QLabel()
        self.audio_label.setObjectName("SmallMuted")
        self.mode_label = QLabel("Mode: scaffold placeholders")
        self.mode_label.setObjectName("SmallMuted")
        self.theme_label = QLabel()
        self.theme_label.setObjectName("SmallMuted")

        layout.addWidget(self.audio_label)
        layout.addStretch(1)
        layout.addWidget(self.mode_label)
        layout.addWidget(self.theme_label)

        self.set_audio_status(audio_status)
        self.set_theme(theme)

    def set_audio_status(self, audio_status: AudioStatus) -> None:
        """Update mocked audio display facts.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self.audio_label.setText(
            f"{audio_status.input_device} | {audio_status.sample_rate} Hz | "
            f"buffer {audio_status.buffer_size}"
        )

    def set_theme(self, theme: Theme) -> None:
        """Update active theme display.

        @author Codex - created for the PySide6 GUI scaffold.
        """

        self.theme_label.setText(f"{theme.name} ({theme.kind})")
