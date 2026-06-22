"""Main menu window for the current desktop GUI."""

from __future__ import annotations

import math
import random
import shutil
import subprocess
from pathlib import Path

import numpy as np
from PySide6.QtCore import QEvent, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter
from PySide6.QtWidgets import (
    QButtonGroup,
    QGraphicsDropShadowEffect,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from interfaces.debug_dump import dump
from interfaces.learn.view import LearnView
from interfaces.play.view import PlayView
from interfaces.sandbox.view import SandboxView


MAIN_MENU_OPTIONS = ("Play", "Learn", "Sandbox")
MENU_OPTION_COLORS = {
    "Play": "#2ee66b",
    "Learn": "#ff4d4d",
    "Sandbox": "#ffd43b",
}
PROJECT_ROOT = Path(__file__).resolve().parents[2]
VISUALIZER_MP3_PATH = PROJECT_ROOT / "assets" / "visualizer" / "on-my-knees.mp3"
MUSIC_LIBRARY_PATH = Path.home() / "Music"
VISUALIZER_AUDIO_EXTENSIONS = {".aac", ".flac", ".m4a", ".mp3", ".ogg", ".wav"}


def choose_visualizer_audio_path(
    music_library_path: Path = MUSIC_LIBRARY_PATH,
    fallback_path: Path = VISUALIZER_MP3_PATH,
) -> Path:
    """Choose a random local song for the decorative menu visualizer.

    Random selection is an interface detail, not a game rule: the menu only
    needs varied spectrum input while the future song library/play use cases
    remain free to define their own catalog and selection policy. The bundled
    fallback keeps the GUI deterministic enough to boot when a user has no
    readable music library.

    @author Codex - added random local music selection for the menu visualizer.
    """

    candidates = [
        path
        for path in music_library_path.rglob("*")
        if path.is_file()
        and path.suffix.lower() in VISUALIZER_AUDIO_EXTENSIONS
        and not any(part.startswith(".") for part in path.relative_to(music_library_path).parts)
    ] if music_library_path.exists() else []
    if not candidates:
        return fallback_path
    return random.choice(candidates)


class VisualizerTrack:
    """Visual-only music data source for the menu spectrum.

    The menu background uses the selected MP3 as its only song-derived texture.
    It intentionally avoids live playback here: audio output belongs to the
    future play use case, while this adapter owns only decorative rendering.

    @author Codex - connected menu spectrum animation to pulled MIDI/MP3 assets.
    @author Codex - switched the menu visualizer to the On My Knees MP3 asset.
    @author Codex - converted visualizer data from volume wave to spectrum frames.
    """

    def __init__(self, mp3_path: Path, bucket_count: int = 768):
        self._sample_rate = 8_000
        self.duration_seconds = 30.0
        self._spectrum_frames = [[0.35 for _ in range(96)]]
        self._load_mp3_spectrum(mp3_path)

    def energy_at(self, seconds: float, bar_index: int, bar_count: int) -> float:
        """Return a normalized visual energy value for a bar at playhead time.

        @author Codex - connected menu spectrum animation to pulled MIDI/MP3 assets.
        @author Codex - switched the menu visualizer to the On My Knees MP3 asset.
        @author Codex - converted visualizer data from volume wave to spectrum frames.
        """

        if not self._spectrum_frames:
            return 0.45
        frame_position = (seconds % self.duration_seconds) / self.duration_seconds
        exact_frame = frame_position * len(self._spectrum_frames)
        frame_index = int(exact_frame) % len(self._spectrum_frames)
        next_frame_index = (frame_index + 1) % len(self._spectrum_frames)
        blend = exact_frame - int(exact_frame)
        current_frame = self._spectrum_frames[frame_index]
        next_frame = self._spectrum_frames[next_frame_index]
        band_position = bar_index / max(bar_count - 1, 1)
        band_index = min(int(band_position * len(current_frame)), len(current_frame) - 1)
        current_energy = current_frame[band_index]
        next_energy = next_frame[band_index]
        return min(1.0, max(0.0, current_energy + ((next_energy - current_energy) * blend)))

    def _load_mp3_spectrum(self, mp3_path: Path) -> None:
        """Decode the MP3 and derive frequency-band frames for the visualizer.

        The menu needs a song-reactive visualizer, not audio playback. Decoding
        through ffmpeg keeps that infrastructure detail outside the future game
        audio policy while avoiding the false signal created by inspecting
        compressed MP3 bytes directly.

        @author Codex - connected menu spectrum animation to pulled MIDI/MP3 assets.
        @author Codex - switched the menu visualizer to the On My Knees MP3 asset.
        @author Codex - replaced compressed-byte texture with decoded MP3 energy.
        @author Codex - converted visualizer data from volume wave to spectrum frames.
        """

        if not mp3_path.exists():
            return
        pcm = self._decode_mp3_to_pcm(mp3_path)
        if not pcm:
            return
        samples = np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32768
        if samples.size == 0:
            return
        self.duration_seconds = max(1.0, samples.size / self._sample_rate)

        window_size = 2048
        hop_size = 256
        band_count = len(self._spectrum_frames[0])
        if samples.size < window_size:
            samples = np.pad(samples, (0, window_size - samples.size))

        window = np.hanning(window_size).astype(np.float32)
        frames: list[list[float]] = []
        for start in range(0, samples.size - window_size + 1, hop_size):
            frame = samples[start : start + window_size] * window
            magnitudes = np.abs(np.fft.rfft(frame))
            frames.append(self._magnitudes_to_bands(magnitudes, band_count))

        peak = max(max(frame) for frame in frames) if frames else 0.0
        if peak <= 0:
            return
        self._spectrum_frames = [
            self._smooth_energy([min(1.0, math.sqrt(value / peak)) for value in frame])
            for frame in frames
        ]

    def _magnitudes_to_bands(self, magnitudes: np.ndarray, band_count: int) -> list[float]:
        """Group FFT magnitudes into visual frequency bands.

        @author Codex - converted visualizer data from volume wave to spectrum frames.
        """

        usable = magnitudes[2:]
        if usable.size == 0:
            return [0.0 for _ in range(band_count)]
        edges = np.geomspace(1, usable.size, band_count + 1).astype(int)
        edges[0] = 0
        bands: list[float] = []
        for index in range(band_count):
            start = int(edges[index])
            end = max(start + 1, int(edges[index + 1]))
            bands.append(float(np.mean(usable[start:end])))
        return bands

    def _decode_mp3_to_pcm(self, mp3_path: Path) -> bytes:
        """Return mono PCM bytes decoded from the MP3, or empty bytes on failure.

        @author Codex - replaced compressed-byte texture with decoded MP3 energy.
        """

        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg is None:
            return b""
        command = [
            ffmpeg,
            "-v",
            "error",
            "-i",
            str(mp3_path),
            "-f",
            "s16le",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(self._sample_rate),
            "-",
        ]
        try:
            result = subprocess.run(command, check=True, capture_output=True)
        except (OSError, subprocess.CalledProcessError):
            return b""
        return result.stdout

    def _smooth_energy(self, energy: list[float]) -> list[float]:
        """Apply light smoothing without flattening song transients.

        @author Codex - replaced compressed-byte texture with decoded MP3 energy.
        """

        smoothed: list[float] = []
        for index, value in enumerate(energy):
            previous_value = energy[index - 1] if index > 0 else value
            next_value = energy[index + 1] if index + 1 < len(energy) else value
            smoothed.append((previous_value * 0.18) + (value * 0.64) + (next_value * 0.18))
        return smoothed


class MainMenuButton(QPushButton):
    """Menu option with plain idle text and lane-colored active glow.

    The visual rule deliberately lives in this adapter widget instead of in the
    menu use case: Qt stylesheets cannot express a real text glow, so the GUI
    detail uses ``QGraphicsDropShadowEffect`` while the menu still exposes only
    stable option labels.

    @author Codex - added lane-colored glow highlight to main menu options.
    """

    def __init__(self, label: str, active_color: str, parent: QWidget | None = None):
        super().__init__(label, parent)
        self._active_color = QColor(active_color)
        self._glow = QGraphicsDropShadowEffect(self)
        self._glow.setBlurRadius(34)
        self._glow.setOffset(0, 0)
        self._glow.setColor(self._with_alpha(self._active_color, 230))
        self.setGraphicsEffect(self._glow)
        self.toggled.connect(lambda checked: self.sync_highlight())
        self.sync_highlight()

    def sync_highlight(self) -> None:
        """Apply active text color and glow from checked, hover, or focus state.

        @author Codex - added lane-colored glow highlight to main menu options.
        """

        active = self.isChecked() or self.underMouse() or self.hasFocus()
        text_color = self._active_color.name() if active else "#ffffff"
        self.setStyleSheet(f"color: {text_color};")
        self._glow.setEnabled(active)

    def _with_alpha(self, color: QColor, alpha: int) -> QColor:
        """Return a copy of ``color`` with the requested alpha channel.

        @author Codex - added lane-colored glow highlight to main menu options.
        """

        copy = QColor(color)
        copy.setAlpha(alpha)
        return copy


class MainMenu(QWidget):
    """Expose the game's top-level navigation choices.

    The menu is intentionally only a navigation boundary for now: each option
    emits a stable screen name, while the destination screens remain deferred
    until their use cases are defined.

    @author Codex - created the replacement main menu interface.
    """

    option_selected = Signal(str)
    option_highlighted = Signal(str)

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
            button = MainMenuButton(label, MENU_OPTION_COLORS[label])
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
                QEvent.Type.Leave,
                QEvent.Type.FocusIn,
                QEvent.Type.FocusOut,
            }:
                button = watched
                if event_type in {QEvent.Type.Enter, QEvent.Type.FocusIn}:
                    self.set_current_index(self._buttons.index(button))
                if isinstance(button, MainMenuButton):
                    button.sync_highlight()
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
        self.option_highlighted.emit(button.text())


class SpectrumBackground(QWidget):
    """Decorative spectrum backdrop driven by the highlighted menu option.

    This is intentionally presentation-only: it does not represent live audio
    and does not leak into menu behavior. The highlighted option only supplies
    the color family used by the gradient.

    @author Codex - added option-colored spectrum background to the main menu.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("spectrumBackground")
        self._active_color = QColor(MENU_OPTION_COLORS["Play"])
        self._phase = 0.0
        self._playhead_seconds = 0.0
        self._audio_path = choose_visualizer_audio_path()
        self._track = VisualizerTrack(self._audio_path)
        self._animation = QTimer(self)
        self._animation.setInterval(33)
        self._animation.timeout.connect(self._advance_animation)
        self._animation.start()

    def set_active_option(self, option: str) -> None:
        """Update the decorative spectrum color from a stable menu option label.

        @author Codex - added option-colored spectrum background to the main menu.
        """

        color = MENU_OPTION_COLORS.get(option)
        if color is None:
            return
        self._active_color = QColor(color)
        self.update()

    def _advance_animation(self) -> None:
        """Advance the decorative spectrum wave and request a repaint.

        @author Codex - animated the option-colored spectrum background.
        """

        self._phase = (self._phase + 0.075) % (math.pi * 2)
        self._playhead_seconds = (self._playhead_seconds + 0.033) % self._track.duration_seconds
        self.update()

    def paintEvent(self, event: object) -> None:
        """Paint a darkened gradient spectrum behind the menu.

        @author Codex - added option-colored spectrum background to the main menu.
        """

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor("#0b0b0b"))

        width = max(self.width(), 1)
        height = max(self.height(), 1)
        bar_count = max(28, min(72, width // 18))
        gap = max(3, width / bar_count * 0.18)
        bar_width = (width - gap * (bar_count + 1)) / bar_count
        baseline = height * 0.86
        max_bar_height = height * 0.58

        for index in range(bar_count):
            position = index / max(bar_count - 1, 1)
            track_texture = self._track.energy_at(self._playhead_seconds, index, bar_count)
            wave = (math.sin(self._phase + position * math.pi * 5.2) + 1.0) / 2.0
            pulse = (math.sin(self._phase * 0.65 + index * 0.31) + 1.0) / 2.0
            drift = (math.sin(self._phase * 1.35 + track_texture * math.pi * 2.0) + 1.0) / 2.0
            strength = 0.07 + (track_texture * 0.84) + (wave * 0.04) + (pulse * 0.03) + (drift * 0.02)
            bar_height = max_bar_height * min(strength, 1.0)
            x = gap + index * (bar_width + gap)
            y = baseline - bar_height

            top_color = self._with_alpha(self._active_color.lighter(135), 128)
            mid_color = self._with_alpha(self._active_color, 82)
            bottom_color = self._with_alpha(self._active_color.darker(170), 18)

            gradient = QLinearGradient(0, y, 0, baseline)
            gradient.setColorAt(0.0, top_color)
            gradient.setColorAt(0.55, mid_color)
            gradient.setColorAt(1.0, bottom_color)

            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(gradient)
            painter.drawRoundedRect(QRectF(x, y, bar_width, bar_height), 4, 4)

        painter.fillRect(self.rect(), QColor(0, 0, 0, 150))

    def _with_alpha(self, color: QColor, alpha: int) -> QColor:
        """Return a copy of ``color`` with the requested alpha channel.

        @author Codex - added option-colored spectrum background to the main menu.
        """

        copy = QColor(color)
        copy.setAlpha(alpha)
        return copy


class MainWindow(QMainWindow):
    """Host the current GUI entry screen.

    @author Codex - created the replacement main menu interface.
    @author Codex - wired Learn mode into the main menu shell.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Guitar Hero")
        self.resize(960, 640)
        self.background = SpectrumBackground()
        self.menu = MainMenu()
        self.play = PlayView()
        self.learn = LearnView()
        self.sandbox = SandboxView()
        self.screens = QStackedWidget()
        self.background_layout = QVBoxLayout(self.background)
        self.background_layout.setContentsMargins(0, 0, 0, 0)
        self.background_layout.addWidget(self.menu)
        self.screens.addWidget(self.background)
        self.screens.addWidget(self.play)
        self.screens.addWidget(self.learn)
        self.screens.addWidget(self.sandbox)
        self.setCentralWidget(self.screens)
        self.menu.option_highlighted.connect(self.background.set_active_option)
        self.menu.option_selected.connect(self._open_option)
        self.play.back_requested.connect(self._show_menu)
        self.learn.back_requested.connect(self._show_menu)
        self.sandbox.back_requested.connect(self._show_menu)
        self.background.set_active_option(MAIN_MENU_OPTIONS[self.menu.current_index()])
        dump("main", "window_ready", initial_option=MAIN_MENU_OPTIONS[self.menu.current_index()])
        self.setStyleSheet(
            """
            QMainWindow, QWidget#spectrumBackground {
                background: #111111;
                color: #f5f5f5;
            }

            QWidget#mainMenu {
                background: transparent;
                color: #f5f5f5;
            }

            QWidget#mainMenuOptions {
                background: transparent;
            }

            QPushButton {
                background: transparent;
                border: 0;
                border-radius: 6px;
                color: #ffffff;
                font-size: 24px;
                font-weight: 650;
                letter-spacing: 0;
                outline: 0;
                padding: 10px 18px;
                text-align: left;
            }

            QPushButton:hover,
            QPushButton:focus,
            QPushButton:checked {
                background: transparent;
                border: 0;
                outline: 0;
            }

            QPushButton:pressed {
                background: transparent;
            }
            """
        )

    def _open_option(self, option: str) -> None:
        """Open the selected top-level screen when the use case exists.

        Sandbox, Learn, and the copied Play starter screen are operational
        destinations. Play intentionally starts as a duplicate so its use case
        can diverge behind its own module boundary.

        @author Codex - wired operational sandbox screen into the main menu.
        @author Codex - wired Learn mode into the main menu shell.
        @author Codex - prevented Learn and Sandbox from sharing live input concurrently.
        @author Codex - wired the copied Play starter module into the menu shell.
        """

        if option == "Play":
            dump("main", "open_option", option=option)
            self.learn.deactivate()
            self.sandbox.stop_input()
            self.screens.setCurrentWidget(self.play)
            self.play.activate()
            return
        if option == "Learn":
            dump("main", "open_option", option=option)
            self.play.deactivate()
            self.sandbox.stop_input()
            self.screens.setCurrentWidget(self.learn)
            self.learn.activate()
            return
        if option == "Sandbox":
            dump("main", "open_option", option=option)
            self.play.deactivate()
            self.learn.deactivate()
            self.screens.setCurrentWidget(self.sandbox)
            if not getattr(self.sandbox, "_running", False):
                self.sandbox.start_input()
            return
        dump("main", "open_option_unimplemented", option=option)

    def _show_menu(self) -> None:
        """Return from an operational screen to the main menu.

        @author Codex - wired operational sandbox screen into the main menu.
        @author Codex - wired Learn mode into the main menu shell.
        @author Codex - stopped active live input when leaving operational screens.
        @author Codex - stopped Play resources when returning to the main menu.
        """

        dump("main", "show_menu")
        self.play.deactivate()
        self.learn.deactivate()
        self.sandbox.stop_input()
        self.screens.setCurrentWidget(self.background)
