"""Qt view for the live audio sandbox."""

from __future__ import annotations

import time

import pyqtgraph as pg

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from interfaces.debug_dump import dump
from interfaces.sandbox.audio_pitch import (
    AudioDevice,
    DetectedPluck,
    LivePitchInput,
    OpenStringFamilyReport,
    PitchFrame,
    PluckDetector,
    SpectrumPeak,
    frequency_to_note,
    list_input_devices,
)


class SpectrumChart(pg.PlotWidget):
    """Mock-style FFT spectrum chart backed by live audio.

    The old throwaway lab used a dark spectrum curve with semantic markers.
    This widget keeps that presentation, but the data comes from real input
    buffers analyzed by the sandbox detector.

    @author Codex - replaced peak bars with mock-style operational spectrum.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._peaks: tuple[SpectrumPeak, ...] = ()
        self._smoothed_magnitudes = None
        self._last_marker_update_at = 0.0
        self.setMinimumHeight(460)
        self.setBackground("#10151f")
        self.showGrid(x=True, y=True, alpha=0.18)
        self.setLabel("left", "Relative magnitude")
        self.setLabel("bottom", "Frequency", units="Hz")
        self.setXRange(60, 1200, padding=0)
        self.setYRange(0, 1.0, padding=0)
        self.curve = self.plot(pen=pg.mkPen("#9bff7a", width=2))
        self.dominant_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#ffb02e", width=2))
        self.fundamental_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#21d4fd", width=2))
        self.addItem(self.dominant_line)
        self.addItem(self.fundamental_line)
        self.dominant_text = pg.TextItem(color="#ffb02e", anchor=(0, 1))
        self.fundamental_text = pg.TextItem(color="#21d4fd", anchor=(0, 1))
        self.addItem(self.dominant_text)
        self.addItem(self.fundamental_text)

    def set_frame(self, frame: PitchFrame) -> None:
        """Render the latest live spectrum and detector markers.

        @author Codex - replaced peak bars with mock-style operational spectrum.
        """

        self._peaks = frame.peaks
        magnitudes = frame.spectrum_magnitudes
        if self._smoothed_magnitudes is None or len(self._smoothed_magnitudes) != len(magnitudes):
            self._smoothed_magnitudes = magnitudes
        else:
            self._smoothed_magnitudes = (self._smoothed_magnitudes * 0.90) + (magnitudes * 0.10)
        self.curve.setData(frame.spectrum_frequencies, self._smoothed_magnitudes)
        now = time.monotonic()
        if now - self._last_marker_update_at < 0.35:
            return
        self._last_marker_update_at = now
        dominant = frame.dominant_peak
        fundamental = frame.likely_fundamental or self._likely_fundamental()
        self._set_marker(self.dominant_line, self.dominant_text, dominant, "Dominant", 0.95)
        self._set_marker(self.fundamental_line, self.fundamental_text, fundamental, "Fundamental", 0.76)

    def _likely_fundamental(self) -> SpectrumPeak | None:
        fundamentals = [peak for peak in self._peaks if peak.harmonic_relationship == "fundamental"]
        if fundamentals:
            return min(fundamentals, key=lambda peak: peak.frequency_hz)
        return self._peaks[0] if self._peaks else None

    def _set_marker(
        self,
        line: pg.InfiniteLine,
        text: pg.TextItem,
        peak: SpectrumPeak | None,
        label: str,
        y: float,
    ) -> None:
        if peak is None:
            line.setVisible(False)
            text.setVisible(False)
            return
        line.setVisible(True)
        text.setVisible(True)
        line.setValue(peak.frequency_hz)
        text.setText(f"{label}: {peak.note} / {peak.frequency_hz:.0f} Hz")
        text.setPos(peak.frequency_hz + 8, y)


class TopPeaksPanel(QFrame):
    """Live peak panel interpreted against the latched pluck event.

    Peak magnitudes remain frame-level evidence, but the annotations follow the
    same event-level note as the detected note panel. That keeps harmonic decay
    understandable without presenting each dominant peak as a new note.

    @author Codex - added realtime top peaks panel with fundamental highlight.
    @author Codex - aligned peak annotations with pluck-level detection.
    @author Codex - changed top peaks from a chart sidebar to an overlay.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("peaksPanel")
        self._current_pluck: DetectedPluck | None = None
        self.setMinimumWidth(520)
        self.setFixedHeight(150)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Maximum)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName("peaksText")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.addWidget(self.text, 1)

    def reset(self) -> None:
        """Clear the latched pluck interpretation.

        @author Codex - aligned peak annotations with pluck-level detection.
        """

        self._current_pluck = None
        self.text.setHtml("<pre>Top peaks:\nWaiting for pluck event</pre>")

    def set_pluck(self, pluck: DetectedPluck) -> None:
        """Use the latest detected pluck as the stable harmonic reference.

        @author Codex - aligned peak annotations with pluck-level detection.
        """

        self._current_pluck = pluck

    def set_frame(self, frame: PitchFrame) -> None:
        """Render live top peaks against the latched detected note.

        @author Codex - added realtime top peaks panel with fundamental highlight.
        @author Codex - aligned peak annotations with pluck-level detection.
        """

        if not frame.peaks:
            return
        lines = ["<pre>Top peaks:"]
        for index, peak in enumerate(frame.peaks[:5], start=1):
            role = self._role_for_peak(peak)
            row = (
                f"{index}. {peak.frequency_hz:6.1f} Hz | {peak.note:4s} | "
                f"MIDI {peak.midi:3d} | {peak.relative_percent:5.0f}%"
            )
            if role == "detected":
                row = f"<span style='color:#21d4fd; font-weight:900;'>{row}  &lt; detected note</span>"
            elif role.startswith("harmonic"):
                row = f"<span style='color:#9bff7a; font-weight:800;'>{row}  &lt; {role}</span>"
            elif index == 1:
                row = f"<span style='color:#ffb02e; font-weight:800;'>{row}  &lt; live dominant</span>"
            lines.append(row)
        lines.append("</pre>")
        self.text.setHtml("\n".join(lines))

    def _role_for_peak(self, peak: SpectrumPeak) -> str:
        if self._current_pluck is None:
            return ""
        base = self._current_pluck.frequency_hz
        if base <= 0:
            return ""
        ratio = peak.frequency_hz / base
        nearest = int(round(ratio))
        if nearest == 1 and abs(peak.frequency_hz - base) / base <= 0.035:
            return "detected"
        if 2 <= nearest <= 6 and abs(peak.frequency_hz - (base * nearest)) / (base * nearest) <= 0.035:
            return f"harmonic {nearest}x"
        return ""


class DetectedPluckPanel(QFrame):
    """Show the latched note event classified from one physical pluck.

    The panel is intentionally event-driven. Live FFT widgets can keep moving
    during decay, but this readout changes only when the pluck detector emits a
    new musical event. It deliberately has no inner title because the note and
    diagnostic detail are the only useful content in this area.

    @author Codex - changed note readout from frame-level updates to pluck events.
    @author Codex - restored Sandbox note readout without the redundant title.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("lastPluckPanel")
        self._last_pluck: DetectedPluck | None = None
        self.setMinimumHeight(150)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)
        self.note = QLabel("--")
        self.note.setObjectName("lastPluckNote")
        self.detail = QLabel("Waiting for pluck event")
        self.detail.setObjectName("lastPluckDetail")
        self.detail.setWordWrap(True)
        layout.addWidget(self.note)
        layout.addWidget(self.detail)

    def reset(self) -> None:
        """Clear the latched event when a new input session starts.

        @author Codex - changed note readout from frame-level updates to pluck events.
        """

        self._last_pluck = None
        self.note.setText("--")
        self.detail.setText("Waiting for pluck event")

    def set_pluck(self, pluck: DetectedPluck) -> None:
        """Render a newly classified pluck without following later FFT frames.

        @author Codex - changed note readout from frame-level updates to pluck events.
        """

        self._last_pluck = pluck
        dominant_midi, dominant_note = frequency_to_note(pluck.dominant_frequency_hz)
        harmonic_text = ", ".join(pluck.harmonic_matches) if pluck.harmonic_matches else "none"
        self.note.setText(f"{pluck.note_name} / {pluck.frequency_hz:.1f} Hz")
        self.detail.setText(
            f"Confidence {pluck.confidence * 100:.0f}% | "
            f"Dominant Peak: {dominant_note} ({pluck.dominant_frequency_hz:.1f} Hz, MIDI {dominant_midi}) | "
            f"Reason: {pluck.reason} | Harmonics: {harmonic_text}"
        )


class OpenStringFamiliesPanel(QFrame):
    """Render open-string family evidence for the last captured pluck.

    The panel is Sandbox-only diagnostic output. It does not replace the
    single-note pluck readout and deliberately avoids chord names because the
    detector only scores standard open-string harmonic families.

    @author Codex - added open-string family diagnostic panel.
    """

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("openStringsPanel")
        self.setMinimumHeight(230)
        self._rows: dict[str, tuple[QLabel, QProgressBar, QLabel]] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(7)
        title = QLabel("Open String Families")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        for string_name in ("E2", "A2", "D3", "G3", "B3", "E4"):
            row = QHBoxLayout()
            row.setSpacing(8)
            name = QLabel(string_name)
            name.setObjectName("openStringName")
            bar = QProgressBar()
            bar.setObjectName("openStringBar")
            bar.setRange(0, 100)
            bar.setTextVisible(False)
            bar.setFixedHeight(12)
            detail = QLabel("0% inactive")
            detail.setObjectName("openStringDetail")
            detail.setMinimumWidth(128)
            row.addWidget(name)
            row.addWidget(bar, 1)
            row.addWidget(detail)
            layout.addLayout(row)
            self._rows[string_name] = (name, bar, detail)
        self.reset()

    def reset(self) -> None:
        """Clear open-string evidence when a new input session starts.

        @author Codex - added open-string family diagnostic panel.
        """

        for string_name, (_name, bar, detail) in self._rows.items():
            bar.setValue(0)
            bar.setToolTip("Waiting for pluck event")
            detail.setText("0% inactive")
            detail.setToolTip("Waiting for pluck event")
            self._set_bar_status(bar, "inactive")

    def set_report(self, report: OpenStringFamilyReport) -> None:
        """Render a latched open-string family report from one pluck.

        @author Codex - added open-string family diagnostic panel.
        """

        for family in report.families:
            row = self._rows.get(family.string_name)
            if row is None:
                continue
            _name, bar, detail = row
            score = int(round(family.score_percent))
            bar.setValue(score)
            bar.setToolTip(family.debug_text)
            detail.setText(f"{score}% {family.status}")
            detail.setToolTip(family.debug_text)
            self._set_bar_status(bar, family.status)

    def _set_bar_status(self, bar: QProgressBar, status: str) -> None:
        color = {
            "active": "#3ddc84",
            "uncertain": "#ffd43b",
            "harmonic overlap": "#21d4fd",
            "inactive": "#5f6875",
        }.get(status, "#5f6875")
        bar.setStyleSheet(
            f"""
            QProgressBar {{
                background: #080b10;
                border: 1px solid #25344a;
                border-radius: 6px;
            }}
            QProgressBar::chunk {{
                background: {color};
                border-radius: 5px;
            }}
            """
        )


class SandboxView(QWidget):
    """Live detector workspace for connected instruments.

    This screen integrates the old FFT pitch detector policy with the useful
    peak chart from the throwaway lab, but it renders real input buffers from
    the selected audio device instead of mock frames.

    @author Codex - created operational sandbox view.
    """

    back_requested = Signal()

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._devices: list[AudioDevice] = []
        self._input = LivePitchInput()
        self._pluck_detector = PluckDetector()
        self._running = False
        self._frame_count = 0
        self._last_readout_at = 0.0

        self.device_combo = QComboBox()
        self.refresh_button = QPushButton("Refresh Devices")
        self.start_button = QPushButton()
        self.start_button.setObjectName("inputToggleButton")
        self.start_button.setAccessibleName("Start input")
        self.start_button.setToolTip("Start input")
        self.back_button = QPushButton("Back")
        self.status_label = QLabel("Select an input device.")
        self.sample_rate_label = QLabel("Sample rate: --")
        self.peak_chart = SpectrumChart()
        self.top_peaks_panel = TopPeaksPanel()
        self.last_pluck_panel = DetectedPluckPanel()
        self.open_strings_panel = OpenStringFamiliesPanel()
        self._update_input_button()

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._update_frame)

        self._build_layout()
        self._apply_style()
        self._connect_signals()
        self.refresh_devices()
        dump("sandbox", "ready")

    def closeEvent(self, event: object) -> None:
        """Stop the audio stream when the widget is closed.

        @author Codex - created operational sandbox view.
        """

        self.stop_input()
        super().closeEvent(event)

    def refresh_devices(self) -> None:
        """Reload available input devices from PortAudio.

        @author Codex - created operational sandbox view.
        """

        self._devices = list_input_devices()
        self.device_combo.clear()
        for device in self._devices:
            self.device_combo.addItem(
                f"[{device.index}] {device.name} ({device.input_channels} in, {device.default_sample_rate} Hz)",
                device.index,
            )
        codec_index = next(
            (index for index, device in enumerate(self._devices) if "codec" in device.name.casefold()),
            -1,
        )
        if codec_index >= 0:
            self.device_combo.setCurrentIndex(codec_index)
        self.start_button.setEnabled(bool(self._devices))
        self.status_label.setText("No input devices found." if not self._devices else "Ready.")
        dump(
            "sandbox",
            "devices_refreshed",
            count=len(self._devices),
            devices=[
                {
                    "index": device.index,
                    "name": device.name,
                    "inputs": device.input_channels,
                    "sample_rate": device.default_sample_rate,
                }
                for device in self._devices
            ],
            selected=self.device_combo.currentData(),
        )
        if self._devices and not self._running:
            QTimer.singleShot(0, self.start_input)

    def start_input(self) -> None:
        """Start live capture from the selected device.

        @author Codex - created operational sandbox view.
        """

        if self._running:
            dump("sandbox", "input_toggle_stop")
            self.stop_input()
            return
        device_index = self.device_combo.currentData()
        if device_index is None:
            self.status_label.setText("No input device selected.")
            dump("sandbox", "input_start_blocked", reason="no_device")
            return
        try:
            dump("sandbox", "input_start_requested", device_index=device_index)
            self._input.start(int(device_index))
        except Exception as exc:
            self.status_label.setText(f"Could not open input: {exc}")
            dump("sandbox", "input_start_failed", device_index=device_index, error=str(exc))
            return
        self._running = True
        self._pluck_detector.reset()
        self.last_pluck_panel.reset()
        self.top_peaks_panel.reset()
        self.open_strings_panel.reset()
        self._update_input_button()
        self.sample_rate_label.setText(f"Sample rate: {self._input.sample_rate} Hz")
        self.status_label.setText("Listening.")
        self._frame_count = 0
        self._last_readout_at = 0.0
        self._timer.start()
        dump("sandbox", "input_started", device_index=device_index, sample_rate=self._input.sample_rate)

    def stop_input(self) -> None:
        """Stop live capture and leave the last frame visible.

        @author Codex - created operational sandbox view.
        """

        self._timer.stop()
        self._input.stop()
        self._running = False
        self._update_input_button()
        self.status_label.setText("Stopped.")
        dump("sandbox", "input_stopped")

    def _update_input_button(self) -> None:
        """Render live input as the control's shape, not an inner icon.

        The sandbox owns the input stream directly, so the transport symbol is
        the whole button: red circle to start capture, white square to stop.

        @author Codex - replaced Sandbox input text with shape-only transport control.
        """

        self.start_button.setText("")
        if self._running:
            self.start_button.setAccessibleName("Stop input")
            self.start_button.setToolTip("Stop input")
            self.start_button.setProperty("inputState", "running")
        else:
            self.start_button.setAccessibleName("Start input")
            self.start_button.setToolTip("Start input")
            self.start_button.setProperty("inputState", "stopped")
        self.start_button.style().unpolish(self.start_button)
        self.start_button.style().polish(self.start_button)

    def _build_layout(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(18, 16, 18, 16)
        root.setSpacing(10)

        top = QHBoxLayout()
        title = QLabel("Sandbox")
        title.setObjectName("title")
        top.addWidget(title)
        top.addStretch(1)
        top.addWidget(self.back_button)
        root.addLayout(top)

        controls = QFrame()
        controls.setObjectName("panel")
        controls_layout = QHBoxLayout(controls)
        controls_layout.setContentsMargins(12, 10, 12, 10)
        controls_layout.addWidget(QLabel("Input"))
        controls_layout.addWidget(self.device_combo, 1)
        controls_layout.addWidget(self.refresh_button)
        controls_layout.addWidget(self.start_button)
        controls_layout.addWidget(self.sample_rate_label)
        root.addWidget(controls)

        self.status_label.setObjectName("status")
        root.addWidget(self.status_label)
        pluck_row = QHBoxLayout()
        pluck_row.setSpacing(10)
        pluck_row.addWidget(self.last_pluck_panel, 1)
        pluck_row.addWidget(self.open_strings_panel, 1)
        root.addLayout(pluck_row, 2)

        chart_title = QLabel("Relative Magnitude / Hz")
        chart_title.setObjectName("sectionTitle")
        root.addWidget(chart_title)
        chart_overlay = QWidget()
        chart_layout = QGridLayout(chart_overlay)
        chart_layout.setContentsMargins(0, 0, 0, 0)
        chart_layout.setSpacing(0)
        chart_layout.addWidget(self.peak_chart, 0, 0)
        chart_layout.addWidget(self.top_peaks_panel, 0, 0, Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight)
        self.top_peaks_panel.raise_()
        root.addWidget(chart_overlay, 8)

    def _connect_signals(self) -> None:
        self.refresh_button.clicked.connect(self.refresh_devices)
        self.start_button.clicked.connect(self.start_input)
        self.back_button.clicked.connect(self._go_back)

    def _go_back(self) -> None:
        self.stop_input()
        self.back_requested.emit()

    def _update_frame(self) -> None:
        frame = self._input.latest_frame()
        if frame is None:
            return
        self._render_frame(frame)

    def _render_frame(self, frame: PitchFrame) -> None:
        pluck = self._pluck_detector.process_frame(frame, time.monotonic())
        if pluck is not None:
            dump(
                "sandbox",
                "pluck",
                note=pluck.note_name,
                midi=pluck.midi,
                frequency_hz=pluck.frequency_hz,
                confidence=pluck.confidence,
                dominant_hz=pluck.dominant_frequency_hz,
                reason=pluck.reason,
                open_strings=_open_string_dump(pluck.open_string_families),
                likely_peak=_peak_dump(frame.likely_fundamental),
                dominant_peak=_peak_dump(frame.dominant_peak),
            )
            self.last_pluck_panel.set_pluck(pluck)
            self.open_strings_panel.set_report(pluck.open_string_families)
            self.top_peaks_panel.set_pluck(pluck)
            self.top_peaks_panel.set_frame(frame)
            self.status_label.setText(f"Detected pluck: {pluck.note_name}.")
        else:
            self.status_label.setText("Listening." if self._pluck_detector.current_pluck else "Listening: waiting for pluck.")
        self.peak_chart.set_frame(frame)
        self._frame_count += 1
        now = time.monotonic()
        if now - self._last_readout_at < 0.75:
            return
        self._last_readout_at = now
        dump(
            "sandbox",
            "frame",
            frame_count=self._frame_count,
            rms=frame.rms,
            confidence=frame.confidence,
            reason=frame.reason,
            likely_peak=_peak_dump(frame.likely_fundamental),
            dominant_peak=_peak_dump(frame.dominant_peak),
        )
        self.top_peaks_panel.set_frame(frame)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget {
                background: #0b0b0b;
                color: #f5f5f5;
                font-family: Inter, Segoe UI, Arial, sans-serif;
                font-size: 13px;
            }
            #title {
                color: #ffd43b;
                font-size: 24px;
                font-weight: 800;
            }
            #panel {
                background: #141414;
                border: 1px solid #2a2a2a;
                border-radius: 8px;
            }
            #sectionTitle {
                color: #b8b8b8;
                font-weight: 800;
            }
            #status {
                color: #b8c7dc;
            }
            QPushButton, QComboBox, QTextEdit {
                background: #181818;
                border: 1px solid #333333;
                border-radius: 6px;
                color: #f5f5f5;
                padding: 7px 9px;
            }
            QPushButton:hover {
                border-color: #ffd43b;
            }
            #inputToggleButton {
                min-width: 34px;
                max-width: 34px;
                min-height: 34px;
                max-height: 34px;
                border-radius: 17px;
                padding: 0;
                background: #ff3b30;
                border: 0;
            }
            #inputToggleButton:hover {
                background: #ff5a52;
                border: 0;
            }
            #inputToggleButton[inputState="running"] {
                border-radius: 4px;
                background: #f5f5f5;
                border: 0;
            }
            #inputToggleButton[inputState="running"]:hover {
                background: #ffffff;
                border: 0;
            }
            #peaksPanel {
                background: #111824;
                border: 1px solid #243043;
                border-radius: 8px;
            }
            #peaksText {
                background: #080b10;
                border: 1px solid #25344a;
                border-radius: 6px;
                color: #d8e2ef;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 12px;
            }
            #lastPluckPanel {
                background: #111824;
                border: 1px solid #243043;
                border-radius: 8px;
            }
            #openStringsPanel {
                background: #111824;
                border: 1px solid #243043;
                border-radius: 8px;
            }
            #openStringName {
                color: #d8e2ef;
                font-family: JetBrains Mono, Consolas, monospace;
                font-weight: 800;
                min-width: 32px;
            }
            #openStringDetail {
                color: #b8c7dc;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 12px;
            }
            #lastPluckNote {
                color: #21d4fd;
                font-size: 42px;
                font-weight: 900;
            }
            #lastPluckDetail {
                color: #b8c7dc;
                font-size: 14px;
            }
            """
        )


def _peak_dump(peak: SpectrumPeak | None) -> dict[str, object] | None:
    """Return compact pitch-peak data for terminal diagnostics.

    @author Codex - added Sandbox terminal debug dump.
    """

    if peak is None:
        return None
    return {
        "note": peak.note,
        "midi": peak.midi,
        "hz": round(peak.frequency_hz, 3),
        "percent": round(getattr(peak, "relative_percent", 0.0), 2),
        "relationship": getattr(peak, "harmonic_relationship", None),
    }


def _open_string_dump(report: OpenStringFamilyReport) -> list[dict[str, object]]:
    """Return active open-string family evidence for terminal diagnostics.

    @author Codex - added Sandbox terminal debug dump.
    """

    return [
        {
            "string": family.string_name,
            "midi": family.midi,
            "score": round(family.score_percent, 2),
            "status": family.status,
        }
        for family in report.ranked
        if family.status != "inactive"
    ][:6]
