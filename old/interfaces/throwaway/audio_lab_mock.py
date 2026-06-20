"""Mock PySide6/PyQtGraph console for the Guitar Hero audio lab.

This module is intentionally isolated from the real detector and minigame
runtime. The business purpose of this screen is to validate the desktop UI
direction with deterministic, inspectable mock data before binding it to
microphones, MIDI files, or scoring engines.
"""

from __future__ import annotations

import argparse
import ctypes
import math
import os
import random
import sys
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np


def prefer_pyside6_qt_libraries() -> None:
    """Prefer PySide6's bundled Qt libraries over system Qt.

    In the current development environment, importing ``PySide6.QtCore`` can
    resolve ``libQt6Core.so.6`` from ``/lib64`` first, which fails because that
    system Qt does not expose the private ABI expected by the installed PySide6
    wheel. Loading PySide6's own QtCore before Qt modules are imported keeps the
    desktop mock runnable without asking users to export ``LD_LIBRARY_PATH``.

    @author Codex - created for the PySide6 mock console.
    """

    if sys.platform.startswith("linux"):
        try:
            import PySide6

            qt_lib_dir = Path(PySide6.__file__).resolve().parent / "Qt" / "lib"
            qt_core = qt_lib_dir / "libQt6Core.so.6"
            if qt_core.exists():
                existing = os.environ.get("LD_LIBRARY_PATH")
                os.environ["LD_LIBRARY_PATH"] = (
                    f"{qt_lib_dir}:{existing}" if existing else str(qt_lib_dir)
                )
                ctypes.CDLL(str(qt_core), mode=ctypes.RTLD_GLOBAL)
        except Exception:
            return


prefer_pyside6_qt_libraries()

import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt, Signal
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMainWindow,
    QPushButton,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)


APP_NAME = "Guitar Hero Audio Lab \u2014 Mock Console"
SAMPLE_RATE = 48_000
BUFFER_SIZE = 1024
UPDATE_INTERVAL_MS = 33

PITCH_CLASSES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]
GUITAR_NOTES = {
    "E2": 82.41,
    "A2": 110.00,
    "D3": 146.83,
    "G3": 196.00,
    "B3": 246.94,
    "E4": 329.63,
}
LANE_NOTES = ["E2", "A2", "D3", "G3", "B3", "E4"]
CHART_SEQUENCE = ["E2", "A2", "D3", "G3", "B3", "E4", "B3", "G3", "D3", "A2"]


@dataclass(frozen=True)
class TopPeak:
    """A ranked spectrum peak shown to explain detector behavior.

    The UI needs explicit peak rows because the mock is not just pretty
    animation; it demonstrates why a dominant-bin detector can choose a
    harmonic while a fundamental-aware detector chooses the intended note.

    @author Codex - created for the PySide6 mock console.
    """

    frequency: float
    note: str
    midi: int
    relative_magnitude: float
    harmonic_relationship: str


@dataclass(frozen=True)
class VisibleNote:
    """A future or recent rhythm marker for the mocked game HUD.

    Parameters are intentionally display-level values so the HUD can stay
    independent from the real minigame engine until that boundary is designed.

    @author Codex - created for the PySide6 mock console.
    """

    note: str
    time_until: float


@dataclass(frozen=True)
class FrameData:
    """Complete UI snapshot for one mock update tick.

    This object is the boundary between mock policy and concrete Qt widgets:
    widgets render a frame but do not decide pitch, scoring, or target-note
    behavior. That keeps the future real detector integration replaceable.

    @author Codex - created for the PySide6 mock console.
    """

    time_axis_ms: np.ndarray
    waveform: np.ndarray
    fft_frequencies: np.ndarray
    fft_magnitudes: np.ndarray
    chroma_values: np.ndarray
    top_peaks: list[TopPeak]
    visible_notes: list[VisibleNote]
    rms: float
    dominant_frequency: float
    dominant_note: str
    dominant_midi: int
    likely_fundamental_frequency: float
    likely_fundamental_note: str
    likely_fundamental_midi: int
    target_note: str
    target_frequency: float
    detected_note: str
    detected_midi: int
    confidence: float
    harmonic_lock: bool
    match_result: str
    timing_offset_ms: float
    timing_feedback: str
    score: int
    combo: int
    accuracy: float
    streak: int
    clipping: bool
    latency_ms: float


def note_to_midi(note: str) -> int:
    """Convert a scientific-pitch note name to MIDI number.

    The mock needs MIDI numbers in the analysis table even before real MIDI
    charts exist, so the conversion remains a small domain helper instead of a
    Qt concern.

    @author Codex - created for the PySide6 mock console.
    """

    pitch = note[:-1]
    octave = int(note[-1])
    return (octave + 1) * 12 + PITCH_CLASSES.index(pitch)


def frequency_to_note(frequency: float) -> tuple[str, int]:
    """Map a frequency to the nearest equal-tempered note.

    This is sufficient for the mock because the purpose is to visualize
    analysis decisions, not to replace the real pitch detector.

    @author Codex - created for the PySide6 mock console.
    """

    midi = int(round(69 + 12 * math.log2(max(frequency, 1e-9) / 440.0)))
    pitch = PITCH_CLASSES[midi % 12]
    octave = midi // 12 - 1
    return f"{pitch}{octave}", midi


def note_frequency(note: str) -> float:
    """Return the configured mock frequency for a guitar-lane note.

    The prototype intentionally supports only the standard-tuning notes that
    appear in the HUD and control panel.

    @author Codex - created for the PySide6 mock console.
    """

    return GUITAR_NOTES[note]


def clamp(value: float, low: float, high: float) -> float:
    """Clamp a numeric UI value into a stable display range.

    Sliders and mock randomness can briefly push generated values past useful
    visual bounds; clamping keeps plots readable without hiding the state.

    @author Codex - created for the PySide6 mock console.
    """

    return max(low, min(high, value))


class MockPitchAnalyzer:
    """Mock pitch policy that contrasts dominant-peak and harmonic-aware modes.

    It exists as a separate class because future real analysis can replace this
    object while the Qt widgets continue consuming the same frame contract.

    @author Codex - created for the PySide6 mock console.
    """

    def analyze(
        self,
        *,
        target_note: str,
        peak_candidates: list[tuple[float, float]],
        mode: str,
        rms: float,
        rms_threshold: float,
        error_enabled: bool,
        difficulty: str,
    ) -> dict[str, Any]:
        """Choose mock dominant and fundamental interpretations for a frame.

        Parameters describe observable signal state and user-selected mode.
        The method returns detector-like facts so the UI can show why harmonic
        lock happens without invoking the real detector.

        @author Codex - created for the PySide6 mock console.
        """

        sorted_peaks = sorted(peak_candidates, key=lambda item: item[1], reverse=True)
        dominant_frequency, dominant_magnitude = sorted_peaks[0]
        dominant_note, dominant_midi = frequency_to_note(dominant_frequency)
        target_frequency = note_frequency(target_note)
        fundamental_note, fundamental_midi = frequency_to_note(target_frequency)

        harmonic_lock = (
            dominant_note != fundamental_note
            and abs(dominant_frequency / target_frequency - round(dominant_frequency / target_frequency)) < 0.18
        )

        random_error_rate = {
            "Easy": 0.02,
            "Medium": 0.05,
            "Hard": 0.08,
            "Expert": 0.12,
        }[difficulty]
        forced_error = error_enabled or random.random() < random_error_rate

        if rms < rms_threshold:
            detected_note = "--"
            detected_midi = -1
            confidence = 0.15
            match_result = "TOO QUIET"
        elif mode == "Dominant Peak":
            detected_note = dominant_note
            detected_midi = dominant_midi
            confidence = 0.74 if harmonic_lock else 0.82
            match_result = "MISS" if detected_note != target_note else "HIT"
        elif mode == "Compare Both":
            detected_note = f"{dominant_note} | {fundamental_note}"
            detected_midi = fundamental_midi
            confidence = 0.91 if harmonic_lock else 0.85
            match_result = "HIT" if fundamental_note == target_note else "MISS"
        else:
            detected_note = fundamental_note
            detected_midi = fundamental_midi
            confidence = 0.94 if harmonic_lock else 0.88
            match_result = "HIT" if fundamental_note == target_note else "MISS"

        if forced_error and match_result == "HIT" and rms >= rms_threshold:
            detected_note = self._neighbor_note(target_note)
            detected_midi = note_to_midi(detected_note)
            confidence = 0.58
            match_result = "MISS"

        if rms >= rms_threshold and match_result not in {"HIT", "MISS"}:
            match_result = "WAITING"

        top_peaks = self._build_top_peaks(sorted_peaks, target_frequency, target_note, dominant_magnitude)
        return {
            "dominant_frequency": dominant_frequency,
            "dominant_note": dominant_note,
            "dominant_midi": dominant_midi,
            "likely_fundamental_frequency": target_frequency,
            "likely_fundamental_note": fundamental_note,
            "likely_fundamental_midi": fundamental_midi,
            "target_frequency": target_frequency,
            "detected_note": detected_note,
            "detected_midi": detected_midi,
            "confidence": clamp(confidence, 0.0, 0.99),
            "harmonic_lock": harmonic_lock,
            "match_result": match_result,
            "top_peaks": top_peaks,
        }

    def _neighbor_note(self, target_note: str) -> str:
        """Return a nearby lane note for mocked detection errors.

        The mock error is lane-local so misses still feel plausible in the game
        HUD instead of jumping to arbitrary pitch classes.

        @author Codex - created for the PySide6 mock console.
        """

        index = LANE_NOTES.index(target_note)
        return LANE_NOTES[(index + 1) % len(LANE_NOTES)]

    def _build_top_peaks(
        self,
        sorted_peaks: list[tuple[float, float]],
        target_frequency: float,
        target_note: str,
        dominant_magnitude: float,
    ) -> list[TopPeak]:
        """Create table rows that explain harmonic relationships.

        The table is a product requirement of this mock, so the analyzer owns
        the labels instead of making the Qt table infer signal meaning.

        @author Codex - created for the PySide6 mock console.
        """

        rows: list[TopPeak] = []
        for frequency, magnitude in sorted_peaks[:5]:
            note, midi = frequency_to_note(frequency)
            ratio = frequency / target_frequency
            nearest = max(1, int(round(ratio)))
            if abs(ratio - 1.0) < 0.18:
                relationship = "fundamental"
            elif abs(ratio - nearest) < 0.18:
                relationship = f"{nearest}x {target_note}"
            else:
                relationship = "neighbor"
            rows.append(
                TopPeak(
                    frequency=frequency,
                    note=note,
                    midi=midi,
                    relative_magnitude=100.0 * magnitude / max(dominant_magnitude, 1e-6),
                    harmonic_relationship=relationship,
                )
            )
        return rows


class MockSignalGenerator:
    """Generate all real-time data needed by the mock audio lab.

    This class is the mocked use case boundary: it simulates audio, pitch
    analysis, and rhythm state without depending on microphone, MIDI, or the
    current CLI game engine.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Initialize deterministic mock state for repeatable visual behavior.

        Keeping a private random generator would reduce demo variation, but the
        UI is meant to feel live; only score and chart state are deterministic.

        @author Codex - created for the PySide6 mock console.
        """

        self.analyzer = MockPitchAnalyzer()
        self.elapsed_seconds = 0.0
        self.last_tick = time.perf_counter()
        self.last_beat_index = -1
        self.score = 0
        self.combo = 0
        self.streak = 0
        self.hits = 0
        self.total_notes = 0
        self.last_timing_offset_ms = 0.0
        self.last_timing_feedback = "WAITING"
        self.last_match_result = "WAITING"

    def reset_score(self) -> None:
        """Reset only rhythm performance counters.

        The simulation clock keeps running so the visual prototype can reset
        scoring without restarting audio or target-note motion.

        @author Codex - created for the PySide6 mock console.
        """

        self.score = 0
        self.combo = 0
        self.streak = 0
        self.hits = 0
        self.total_notes = 0
        self.last_timing_offset_ms = 0.0
        self.last_timing_feedback = "WAITING"
        self.last_match_result = "WAITING"

    def reset_clock(self) -> None:
        """Restart mock time while preserving current control settings.

        This supports the top-level Start action without requiring any real
        audio resource acquisition.

        @author Codex - created for the PySide6 mock console.
        """

        self.elapsed_seconds = 0.0
        self.last_tick = time.perf_counter()
        self.last_beat_index = -1

    def generate_frame(self, settings: dict[str, Any]) -> FrameData:
        """Advance mock time and return one complete UI frame.

        The returned frame includes waveform, spectrum, chroma, detector facts,
        and game HUD state so widgets stay passive and replaceable.

        @author Codex - created for the PySide6 mock console.
        """

        now = time.perf_counter()
        dt = clamp(now - self.last_tick, 0.0, 0.08)
        self.last_tick = now
        self.elapsed_seconds += dt

        tempo_bpm = float(settings["tempo_bpm"])
        beat_duration = 60.0 / max(tempo_bpm, 1.0)
        beat_index = int(self.elapsed_seconds / beat_duration)
        phase = (self.elapsed_seconds % beat_duration) / beat_duration
        target_note = self._target_for_index(beat_index, settings)

        waveform, time_axis_ms, rms, clipping = self._waveform(target_note, settings)
        fft_frequencies, fft_magnitudes, peak_candidates = self._spectrum(target_note, settings)

        analysis = self.analyzer.analyze(
            target_note=target_note,
            peak_candidates=peak_candidates,
            mode=settings["pitch_mode"],
            rms=rms,
            rms_threshold=settings["rms_threshold"],
            error_enabled=settings["mock_error"],
            difficulty=settings["difficulty"],
        )

        if beat_index != self.last_beat_index:
            self._score_beat(analysis["match_result"], settings["difficulty"])
            self.last_beat_index = beat_index

        chroma_values = self._chroma(analysis["top_peaks"], target_note, phase)
        visible_notes = self._visible_notes(beat_index, beat_duration, settings)
        accuracy = 100.0 * self.hits / max(self.total_notes, 1)
        latency_ms = (BUFFER_SIZE / SAMPLE_RATE) * 1000.0 + 4.0 + settings["noise_level"] * 3.0

        return FrameData(
            time_axis_ms=time_axis_ms,
            waveform=waveform,
            fft_frequencies=fft_frequencies,
            fft_magnitudes=fft_magnitudes,
            chroma_values=chroma_values,
            top_peaks=analysis["top_peaks"],
            visible_notes=visible_notes,
            rms=rms,
            dominant_frequency=analysis["dominant_frequency"],
            dominant_note=analysis["dominant_note"],
            dominant_midi=analysis["dominant_midi"],
            likely_fundamental_frequency=analysis["likely_fundamental_frequency"],
            likely_fundamental_note=analysis["likely_fundamental_note"],
            likely_fundamental_midi=analysis["likely_fundamental_midi"],
            target_note=target_note,
            target_frequency=analysis["target_frequency"],
            detected_note=analysis["detected_note"],
            detected_midi=analysis["detected_midi"],
            confidence=analysis["confidence"],
            harmonic_lock=analysis["harmonic_lock"],
            match_result=self.last_match_result,
            timing_offset_ms=self.last_timing_offset_ms,
            timing_feedback=self.last_timing_feedback,
            score=self.score,
            combo=self.combo,
            accuracy=accuracy,
            streak=self.streak,
            clipping=clipping,
            latency_ms=latency_ms,
        )

    def _score_beat(self, match_result: str, difficulty: str) -> None:
        """Apply mocked rhythm scoring at beat boundaries.

        Scoring changes only once per target note so the HUD behaves like a
        rhythm game instead of awarding points every animation frame.

        @author Codex - created for the PySide6 mock console.
        """

        if self.last_beat_index < 0:
            self.last_match_result = "WAITING"
            return

        self.total_notes += 1
        jitter_ranges = {
            "Easy": 28,
            "Medium": 44,
            "Hard": 62,
            "Expert": 82,
        }
        offset = random.uniform(-jitter_ranges[difficulty], jitter_ranges[difficulty])
        self.last_timing_offset_ms = offset

        if match_result == "HIT":
            self.hits += 1
            self.combo += 1
            self.streak = max(self.streak, self.combo)
            multiplier = 1 + self.combo // 10
            self.score += 100 * multiplier
            self.last_timing_feedback = "PERFECT" if abs(offset) <= 25 else "GOOD"
            self.last_match_result = "HIT"
        elif match_result == "TOO QUIET":
            self.combo = 0
            self.last_timing_feedback = "MISS"
            self.last_match_result = "TOO QUIET"
        else:
            self.combo = 0
            self.last_timing_feedback = "LATE" if offset > 0 else "MISS"
            self.last_match_result = "MISS"

    def _target_for_index(self, index: int, settings: dict[str, Any]) -> str:
        """Return the active target note for the selected mock source.

        This keeps target-source behavior out of widgets and mirrors the future
        boundary where manual notes, MIDI charts, and trainers will differ.

        @author Codex - created for the PySide6 mock console.
        """

        source = settings["target_source"]
        if source == "Manual Note":
            return settings["manual_target_note"]
        if source == "Random String Trainer":
            return random.Random(index // 2).choice(LANE_NOTES)
        return CHART_SEQUENCE[index % len(CHART_SEQUENCE)]

    def _visible_notes(
        self,
        beat_index: int,
        beat_duration: float,
        settings: dict[str, Any],
    ) -> list[VisibleNote]:
        """Create note markers around the hit line for the game HUD.

        The HUD receives relative timing rather than chart indices so it can be
        replaced by a real minigame adapter later.

        @author Codex - created for the PySide6 mock console.
        """

        current_beat_time = beat_index * beat_duration
        notes: list[VisibleNote] = []
        for index in range(max(0, beat_index - 2), beat_index + 12):
            note_time = index * beat_duration
            time_until = note_time - self.elapsed_seconds
            if -0.7 <= time_until <= 3.8:
                notes.append(VisibleNote(note=self._target_for_index(index, settings), time_until=time_until))
        return notes

    def _waveform(
        self,
        target_note: str,
        settings: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, float, bool]:
        """Generate a guitar-like waveform buffer for the live plot.

        Strong third harmonics intentionally appear on low E so the prototype
        demonstrates the real harmonic-lock problem.

        @author Codex - created for the PySide6 mock console.
        """

        t = (np.arange(BUFFER_SIZE) / SAMPLE_RATE) + self.elapsed_seconds
        fundamental = note_frequency(target_note)
        harmonic_strength = settings["harmonic_strength"]
        noise_level = settings["noise_level"]
        envelope = 0.55 + 0.25 * math.sin(self.elapsed_seconds * 2.0 * math.pi * 1.7)
        base_gain = 0.44 + harmonic_strength * 0.16
        waveform = (
            base_gain * envelope * np.sin(2.0 * np.pi * fundamental * t)
            + (0.22 + harmonic_strength * 0.18) * np.sin(2.0 * np.pi * 2.0 * fundamental * t + 0.4)
            + (0.30 + harmonic_strength * 0.42) * np.sin(2.0 * np.pi * 3.0 * fundamental * t + 1.1)
            + 0.10 * np.sin(2.0 * np.pi * 4.0 * fundamental * t + 2.0)
        )
        waveform += np.random.normal(0.0, 0.018 + noise_level * 0.07, BUFFER_SIZE)
        waveform *= 0.72
        rms = float(np.sqrt(np.mean(np.square(waveform))))
        clipping = bool(np.max(np.abs(waveform)) > 0.95)
        time_axis_ms = (np.arange(BUFFER_SIZE) - BUFFER_SIZE) / SAMPLE_RATE * 1000.0
        return waveform.astype(float), time_axis_ms.astype(float), rms, clipping

    def _spectrum(
        self,
        target_note: str,
        settings: dict[str, Any],
    ) -> tuple[np.ndarray, np.ndarray, list[tuple[float, float]]]:
        """Generate a mock FFT with guitar-like harmonic peaks.

        The low E profile deliberately shows a stronger B3-region third
        harmonic than the 82 Hz fundamental to make detector modes comparable.

        @author Codex - created for the PySide6 mock console.
        """

        frequencies = np.linspace(60.0, 1200.0, 720)
        target_frequency = note_frequency(target_note)
        harmonic_strength = settings["harmonic_strength"]
        noise_level = settings["noise_level"]

        magnitudes = np.random.normal(0.025 + noise_level * 0.05, 0.008 + noise_level * 0.012, len(frequencies))
        magnitudes = np.maximum(magnitudes, 0.0)

        peak_candidates: list[tuple[float, float]] = []
        harmonic_weights = [0.56, 0.38, 1.0 if target_note == "E2" else 0.54, 0.23, 0.16, 0.20]
        for harmonic, base_weight in enumerate(harmonic_weights, start=1):
            peak_frequency = target_frequency * harmonic
            if peak_frequency > 1200.0:
                continue
            wobble = math.sin(self.elapsed_seconds * (1.3 + harmonic * 0.1)) * (0.6 + 0.15 * harmonic)
            visible_frequency = peak_frequency + wobble
            weight = base_weight * (0.76 + harmonic_strength * 0.44)
            if harmonic == 1:
                weight *= 1.05 - harmonic_strength * 0.22
            if harmonic == 3:
                weight *= 0.90 + harmonic_strength * 0.35
            width = 4.0 + harmonic * 1.6
            magnitudes += weight * np.exp(-0.5 * np.square((frequencies - visible_frequency) / width))
            peak_candidates.append((visible_frequency, weight))

        expected = note_frequency(settings["manual_target_note"])
        if settings["target_source"] == "Manual Note" and settings["manual_target_note"] != target_note:
            magnitudes += 0.2 * np.exp(-0.5 * np.square((frequencies - expected) / 5.0))

        magnitudes = magnitudes / max(float(np.max(magnitudes)), 1e-6)
        return frequencies.astype(float), magnitudes.astype(float), peak_candidates

    def _chroma(self, top_peaks: list[TopPeak], target_note: str, phase: float) -> np.ndarray:
        """Build 12 pitch-class bars from the mock peak table.

        Chroma is derived from analysis peaks because this panel previews future
        chord detection rather than raw waveform drawing.

        @author Codex - created for the PySide6 mock console.
        """

        values = np.random.uniform(0.03, 0.10, len(PITCH_CLASSES))
        for peak in top_peaks:
            pitch = peak.note[:-1]
            if pitch in PITCH_CLASSES:
                values[PITCH_CLASSES.index(pitch)] += peak.relative_magnitude / 130.0
        target_pitch = target_note[:-1]
        values[PITCH_CLASSES.index(target_pitch)] += 0.18 + 0.08 * math.sin(phase * math.pi)
        return np.clip(values, 0.0, 1.0).astype(float)


class WaveformPlot(pg.PlotWidget):
    """Live waveform panel for mocked input amplitude.

    The plot owns only visual configuration and accepts frame data from the
    mock use case boundary.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Configure the dark waveform plot and clipping label.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setBackground("#10151f")
        self.showGrid(x=True, y=True, alpha=0.18)
        self.setLabel("left", "Amplitude")
        self.setLabel("bottom", "Time", units="ms")
        self.setYRange(-1.15, 1.15)
        self.curve = self.plot(pen=pg.mkPen("#21d4fd", width=2))
        self.clip_text = pg.TextItem("CLIPPING", color="#ff5c6c", anchor=(1, 0))
        self.addItem(self.clip_text)
        self.clip_text.setPos(-2.0, 0.98)
        self.clip_text.setVisible(False)

    def update_frame(self, frame: FrameData) -> None:
        """Render waveform samples for the current mock frame.

        @author Codex - created for the PySide6 mock console.
        """

        self.curve.setData(frame.time_axis_ms, frame.waveform)
        self.clip_text.setVisible(frame.clipping)


class SpectrumPlot(pg.PlotWidget):
    """FFT spectrum panel with dominant, fundamental, and target markers.

    The marker set makes the harmonic-lock case visible, especially for low E.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Configure the spectrum plot and marker items.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setBackground("#10151f")
        self.showGrid(x=True, y=True, alpha=0.18)
        self.setLabel("left", "Relative magnitude")
        self.setLabel("bottom", "Frequency", units="Hz")
        self.setXRange(60, 1200)
        self.setYRange(0, 1.15)
        self.curve = self.plot(pen=pg.mkPen("#9bff7a", width=2))
        self.dominant_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#ffb02e", width=2))
        self.fundamental_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#21d4fd", width=2))
        self.target_line = pg.InfiniteLine(angle=90, movable=False, pen=pg.mkPen("#d879ff", width=2, style=Qt.PenStyle.DashLine))
        self.addItem(self.dominant_line)
        self.addItem(self.fundamental_line)
        self.addItem(self.target_line)
        self.dominant_text = pg.TextItem(color="#ffb02e", anchor=(0, 1))
        self.fundamental_text = pg.TextItem(color="#21d4fd", anchor=(0, 1))
        self.target_text = pg.TextItem(color="#d879ff", anchor=(0, 1))
        self.addItem(self.dominant_text)
        self.addItem(self.fundamental_text)
        self.addItem(self.target_text)

    def update_frame(self, frame: FrameData) -> None:
        """Render the FFT curve and frequency markers.

        @author Codex - created for the PySide6 mock console.
        """

        self.curve.setData(frame.fft_frequencies, frame.fft_magnitudes)
        self.dominant_line.setValue(frame.dominant_frequency)
        self.fundamental_line.setValue(frame.likely_fundamental_frequency)
        self.target_line.setValue(frame.target_frequency)
        self.dominant_text.setText(f"Dominant: {frame.dominant_note} / {frame.dominant_frequency:.0f} Hz")
        self.fundamental_text.setText(
            f"Fundamental: {frame.likely_fundamental_note} / {frame.likely_fundamental_frequency:.0f} Hz"
        )
        self.target_text.setText(f"Target: {frame.target_note}")
        self.dominant_text.setPos(frame.dominant_frequency + 8, 1.05)
        self.fundamental_text.setPos(frame.likely_fundamental_frequency + 8, 0.86)
        self.target_text.setPos(frame.target_frequency + 8, 0.68)


class ChromaPlot(pg.PlotWidget):
    """Animated chroma bars for future pitch-class and chord detection.

    Chroma is visually separate from the FFT so the prototype can show both
    spectral evidence and musical class evidence.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Configure a 12-bar pitch-class plot.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setBackground("#10151f")
        self.showGrid(x=False, y=True, alpha=0.15)
        self.setLabel("left", "Activity")
        self.setYRange(0, 1.05)
        axis = self.getAxis("bottom")
        axis.setTicks([[(index, name) for index, name in enumerate(PITCH_CLASSES)]])
        brushes = [pg.mkBrush("#243043") for _ in PITCH_CLASSES]
        self.bars = pg.BarGraphItem(x=np.arange(12), height=np.zeros(12), width=0.72, brushes=brushes)
        self.addItem(self.bars)

    def update_frame(self, frame: FrameData) -> None:
        """Render pitch-class bar activity for the current mock frame.

        @author Codex - created for the PySide6 mock console.
        """

        brushes = []
        for value, name in zip(frame.chroma_values, PITCH_CLASSES):
            if name == frame.target_note[:-1]:
                brushes.append(pg.mkBrush("#d879ff"))
            elif value > 0.45:
                brushes.append(pg.mkBrush("#21d4fd"))
            else:
                brushes.append(pg.mkBrush("#243043"))
        self.bars.setOpts(height=frame.chroma_values, brushes=brushes)


class AnalysisPanel(QFrame):
    """Right-side analysis cards and top peak table.

    This panel is read-only; it renders detector facts supplied by the frame
    contract and does not infer pitch policy on its own.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Build analysis cards and the FFT peak table.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setObjectName("panel")
        self.setMinimumWidth(330)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Analysis")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.cards: dict[str, QLabel] = {}
        grid = QGridLayout()
        grid.setSpacing(8)
        card_defs = [
            ("rms", "RMS level"),
            ("dominant_frequency", "Dominant peak"),
            ("dominant_note", "Dominant note"),
            ("fundamental_frequency", "Likely fundamental"),
            ("fundamental_note", "Fundamental note"),
            ("midi_note", "MIDI note"),
            ("confidence", "Confidence"),
            ("harmonic_lock", "Harmonic lock"),
            ("target", "Current target"),
            ("match_result", "Match result"),
            ("timing", "Timing offset"),
        ]
        for index, (key, label) in enumerate(card_defs):
            card, value_label = self._make_card(label)
            self.cards[key] = value_label
            grid.addWidget(card, index // 2, index % 2)
        layout.addLayout(grid)

        table_title = QLabel("Top FFT Peaks")
        table_title.setObjectName("sectionTitle")
        layout.addWidget(table_title)

        self.table = QTableWidget(5, 6)
        self.table.setHorizontalHeaderLabels(
            ["Rank", "Frequency", "Note", "MIDI", "Relative magnitude", "Harmonic relationship"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table, 1)

    def _make_card(self, title: str) -> tuple[QFrame, QLabel]:
        """Create one compact metric card.

        Cards use consistent structure so state colors can be applied only to
        values that need semantic emphasis.

        @author Codex - created for the PySide6 mock console.
        """

        card = QFrame()
        card.setObjectName("metricCard")
        box = QVBoxLayout(card)
        box.setContentsMargins(10, 8, 10, 8)
        box.setSpacing(4)
        title_label = QLabel(title)
        title_label.setObjectName("metricTitle")
        value_label = QLabel("--")
        value_label.setObjectName("metricValue")
        value_label.setMinimumHeight(24)
        value_label.setWordWrap(True)
        box.addWidget(title_label)
        box.addWidget(value_label)
        return card, value_label

    def update_frame(self, frame: FrameData) -> None:
        """Render cards and top peak rows for the current frame.

        @author Codex - created for the PySide6 mock console.
        """

        values = {
            "rms": f"{frame.rms:.3f}",
            "dominant_frequency": f"{frame.dominant_frequency:.1f} Hz",
            "dominant_note": frame.dominant_note,
            "fundamental_frequency": f"{frame.likely_fundamental_frequency:.1f} Hz",
            "fundamental_note": frame.likely_fundamental_note,
            "midi_note": str(frame.detected_midi) if frame.detected_midi >= 0 else "--",
            "confidence": f"{frame.confidence * 100:.0f}%",
            "harmonic_lock": "WARNING" if frame.harmonic_lock else "clear",
            "target": frame.target_note,
            "match_result": frame.match_result,
            "timing": f"{frame.timing_offset_ms:+.0f} ms",
        }
        for key, value in values.items():
            self.cards[key].setText(value)

        self._set_value_color("match_result", frame.match_result)
        self.cards["harmonic_lock"].setStyleSheet(
            "color: #ffb02e;" if frame.harmonic_lock else "color: #7ee787;"
        )

        for row, peak in enumerate(frame.top_peaks):
            cells = [
                str(row + 1),
                f"{peak.frequency:.1f} Hz",
                peak.note,
                str(peak.midi),
                f"{peak.relative_magnitude:.0f}%",
                peak.harmonic_relationship,
            ]
            for column, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.table.setItem(row, column, item)

    def _set_value_color(self, key: str, state: str) -> None:
        """Apply semantic color to a metric value.

        Color is attached to state names rather than widget position so future
        layout changes do not break status semantics.

        @author Codex - created for the PySide6 mock console.
        """

        colors = {
            "HIT": "#7ee787",
            "PERFECT": "#7ee787",
            "GOOD": "#f7d774",
            "WAITING": "#9fb3c8",
            "TOO QUIET": "#ffb02e",
            "MISS": "#ff5c6c",
            "LATE": "#ffb02e",
        }
        self.cards[key].setStyleSheet(f"color: {colors.get(state, '#d8e2ef')};")


class ControlPanel(QFrame):
    """Left-side controls that tune the mock scenario.

    The panel emits settings dictionaries instead of mutating plots directly,
    preserving a boundary between interaction and mock audio policy.

    @author Codex - created for the PySide6 mock console.
    """

    settingsChanged = Signal(dict)
    actionTriggered = Signal(str)

    def __init__(self) -> None:
        """Build all requested controls for the audio lab prototype.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setObjectName("panel")
        self.setMinimumWidth(270)
        self.setMaximumWidth(330)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel("Controls")
        title.setObjectName("panelTitle")
        layout.addWidget(title)

        self.input_device = self._combo(["USB Audio CODEC", "Built-in Microphone", "Mock Sine Generator", "Mock Guitar Harmonics"])
        layout.addWidget(self._labeled("Input device", self.input_device))

        pitch_label = QLabel("Pitch mode")
        pitch_label.setObjectName("controlLabel")
        layout.addWidget(pitch_label)
        self.pitch_group = QButtonGroup(self)
        self.pitch_buttons: dict[str, QPushButton] = {}
        pitch_row = QHBoxLayout()
        for text in ["Dominant Peak", "Fundamental/Harmonic-aware", "Compare Both"]:
            button = QPushButton(text)
            button.setCheckable(True)
            button.setObjectName("segmentButton")
            self.pitch_group.addButton(button)
            self.pitch_buttons[text] = button
            pitch_row.addWidget(button)
        self.pitch_buttons["Compare Both"].setChecked(True)
        layout.addLayout(pitch_row)

        self.instrument_profile = self._combo(["Guitar Standard Tuning", "Bass", "Piano", "Voice"])
        layout.addWidget(self._labeled("Instrument profile", self.instrument_profile))

        self.rms_slider, self.rms_value = self._slider(0, 100, 24)
        layout.addWidget(self._labeled("RMS threshold", self._slider_with_value(self.rms_slider, self.rms_value)))

        self.noise_slider, self.noise_value = self._slider(0, 100, 18)
        layout.addWidget(self._labeled("Noise level", self._slider_with_value(self.noise_slider, self.noise_value)))

        self.harmonic_slider, self.harmonic_value = self._slider(0, 100, 72)
        layout.addWidget(self._labeled("Harmonic strength", self._slider_with_value(self.harmonic_slider, self.harmonic_value)))

        self.tempo_slider, self.tempo_value = self._slider(60, 180, 112)
        layout.addWidget(self._labeled("Tempo / BPM", self._slider_with_value(self.tempo_slider, self.tempo_value)))

        self.difficulty = self._combo(["Easy", "Medium", "Hard", "Expert"])
        self.difficulty.setCurrentText("Hard")
        layout.addWidget(self._labeled("Difficulty", self.difficulty))

        self.target_source = self._combo(["Manual Note", "Mock MIDI Chart", "Random String Trainer"])
        self.target_source.setCurrentText("Mock MIDI Chart")
        layout.addWidget(self._labeled("Target source", self.target_source))

        self.manual_target_note = self._combo(LANE_NOTES)
        layout.addWidget(self._labeled("Manual target note", self.manual_target_note))

        button_grid = QGridLayout()
        actions = [
            ("Calibrate Noise Floor", "calibrate"),
            ("Freeze Frame", "freeze"),
            ("Reset Score", "reset_score"),
            ("Toggle Mock Error", "toggle_error"),
            ("Export Screenshot placeholder", "export_screenshot"),
        ]
        for index, (text, action) in enumerate(actions):
            button = QPushButton(text)
            if action in {"freeze", "toggle_error"}:
                button.setCheckable(True)
            button.clicked.connect(lambda _checked=False, name=action: self.actionTriggered.emit(name))
            button_grid.addWidget(button, index // 2, index % 2)
        layout.addLayout(button_grid)
        layout.addStretch(1)

        self._connect_settings()
        self._update_slider_labels()

    def _combo(self, values: list[str]) -> QComboBox:
        """Create a consistent combo box for mock configuration.

        @author Codex - created for the PySide6 mock console.
        """

        combo = QComboBox()
        combo.addItems(values)
        return combo

    def _slider(self, minimum: int, maximum: int, value: int) -> tuple[QSlider, QLabel]:
        """Create a horizontal slider with its live value label.

        @author Codex - created for the PySide6 mock console.
        """

        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(minimum, maximum)
        slider.setValue(value)
        slider.setSingleStep(1)
        value_label = QLabel()
        value_label.setObjectName("sliderValue")
        value_label.setMinimumWidth(42)
        value_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        return slider, value_label

    def _slider_with_value(self, slider: QSlider, value_label: QLabel) -> QWidget:
        """Pack a slider and value label into one control row.

        @author Codex - created for the PySide6 mock console.
        """

        container = QWidget()
        row = QHBoxLayout(container)
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(slider, 1)
        row.addWidget(value_label)
        return container

    def _labeled(self, label: str, widget: QWidget) -> QWidget:
        """Create a label/control block for the left panel.

        @author Codex - created for the PySide6 mock console.
        """

        container = QWidget()
        box = QVBoxLayout(container)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        label_widget = QLabel(label)
        label_widget.setObjectName("controlLabel")
        box.addWidget(label_widget)
        box.addWidget(widget)
        return container

    def _connect_settings(self) -> None:
        """Wire controls to emit a complete settings snapshot.

        Emitting snapshots avoids hidden partial state and makes the mock
        generator easy to replace with a real use case adapter later.

        @author Codex - created for the PySide6 mock console.
        """

        for combo in [self.input_device, self.instrument_profile, self.difficulty, self.target_source, self.manual_target_note]:
            combo.currentTextChanged.connect(self._emit_settings)
        for slider in [self.rms_slider, self.noise_slider, self.harmonic_slider, self.tempo_slider]:
            slider.valueChanged.connect(self._emit_settings)
            slider.valueChanged.connect(self._update_slider_labels)
        self.pitch_group.buttonClicked.connect(self._emit_settings)

    def _update_slider_labels(self, *_args: Any) -> None:
        """Show human-readable slider values.

        @author Codex - created for the PySide6 mock console.
        """

        self.rms_value.setText(f"{self.rms_slider.value() / 100:.2f}")
        self.noise_value.setText(f"{self.noise_slider.value()}%")
        self.harmonic_value.setText(f"{self.harmonic_slider.value()}%")
        self.tempo_value.setText(str(self.tempo_slider.value()))

    def _emit_settings(self, *_args: Any) -> None:
        """Emit current settings after any control change.

        @author Codex - created for the PySide6 mock console.
        """

        self.settingsChanged.emit(self.settings())

    def settings(self) -> dict[str, Any]:
        """Return normalized mock settings for the generator.

        UI labels remain human-readable while the generator receives numeric
        values in stable ranges.

        @author Codex - created for the PySide6 mock console.
        """

        pitch_mode = next(text for text, button in self.pitch_buttons.items() if button.isChecked())
        return {
            "input_device": self.input_device.currentText(),
            "pitch_mode": pitch_mode,
            "instrument_profile": self.instrument_profile.currentText(),
            "rms_threshold": self.rms_slider.value() / 100.0,
            "noise_level": self.noise_slider.value() / 100.0,
            "harmonic_strength": self.harmonic_slider.value() / 100.0,
            "tempo_bpm": self.tempo_slider.value(),
            "difficulty": self.difficulty.currentText(),
            "target_source": self.target_source.currentText(),
            "manual_target_note": self.manual_target_note.currentText(),
            "mock_error": False,
        }

    def set_calibrated_threshold(self) -> None:
        """Set the RMS threshold from the current mock noise setting.

        Calibration is a placeholder for the future real noise-floor use case;
        it changes the threshold enough for users to see behavior respond.

        @author Codex - created for the PySide6 mock console.
        """

        value = int(clamp(14 + self.noise_slider.value() * 0.42, 8, 70))
        self.rms_slider.setValue(value)
        self._emit_settings()


class EventLog(QFrame):
    """Timestamped event log for simulated detector and game messages.

    The log gives users auditability for mode changes and mock detector
    decisions without coupling logs to the underlying widgets.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Create the scrolling log panel.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setObjectName("panel")
        self.setMinimumHeight(130)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 14)
        layout.setSpacing(8)
        title = QLabel("Event Log")
        title.setObjectName("sectionTitle")
        layout.addWidget(title)
        self.text = QTextEdit()
        self.text.setReadOnly(True)
        self.text.setObjectName("eventLog")
        layout.addWidget(self.text)

    def add_message(self, message: str) -> None:
        """Append one timestamped log message.

        @author Codex - created for the PySide6 mock console.
        """

        timestamp = datetime.now().strftime("%H:%M:%S")
        self.text.append(f"[{timestamp}] {message}")
        scrollbar = self.text.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


class AudioLabMockWindow(QMainWindow):
    """Main desktop window for the mocked Guitar Hero audio lab.

    The window composes panels and owns application timing; mock audio policy is
    delegated to ``MockSignalGenerator`` so future real adapters have one place
    to plug in.

    @author Codex - created for the PySide6 mock console.
    """

    def __init__(self) -> None:
        """Build the dashboard and start the mock simulation timer.

        @author Codex - created for the PySide6 mock console.
        """

        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.resize(1600, 1000)
        self.generator = MockSignalGenerator()
        self.current_settings: dict[str, Any] = {}
        self.running = True
        self.frozen = False
        self.mock_error = False
        self.fps_samples: deque[float] = deque(maxlen=30)
        self.last_frame_time = time.perf_counter()
        self.last_harmonic_lock = False
        self.last_match_result = "WAITING"

        self.control_panel = ControlPanel()
        self.waveform_plot = WaveformPlot()
        self.spectrum_plot = SpectrumPlot()
        self.chroma_plot = ChromaPlot()
        self.analysis_panel = AnalysisPanel()
        self.event_log = EventLog()

        self._build_layout()
        self._apply_style()
        self._connect_signals()
        self.current_settings = self.control_panel.settings()

        self.timer = QTimer(self)
        self.timer.setInterval(UPDATE_INTERVAL_MS)
        self.timer.timeout.connect(self._on_timer)
        self.timer.start()

        self.event_log.add_message("Simulation started")
        self.event_log.add_message("Mock device selected: USB Audio CODEC")
        self._install_shortcuts()

    def _build_layout(self) -> None:
        """Assemble the dashboard regions requested by the prototype.

        @author Codex - created for the PySide6 mock console.
        """

        root = QWidget()
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(10, 10, 10, 10)
        root_layout.setSpacing(10)
        root_layout.addWidget(self._top_status_bar())

        body_splitter = QSplitter(Qt.Orientation.Horizontal)
        body_splitter.addWidget(self.control_panel)

        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(0, 0, 0, 0)
        center_layout.setSpacing(10)
        self.waveform_plot.setMinimumHeight(210)
        self.spectrum_plot.setMinimumHeight(260)
        self.chroma_plot.setMinimumHeight(180)
        center_layout.addWidget(self.waveform_plot, 3)
        center_layout.addWidget(self.spectrum_plot, 4)
        center_layout.addWidget(self.chroma_plot, 2)
        body_splitter.addWidget(center)
        body_splitter.addWidget(self.analysis_panel)
        body_splitter.setStretchFactor(0, 0)
        body_splitter.setStretchFactor(1, 1)
        body_splitter.setStretchFactor(2, 0)

        bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        bottom_splitter.addWidget(body_splitter)
        bottom_splitter.addWidget(self.event_log)
        bottom_splitter.setStretchFactor(0, 4)
        bottom_splitter.setStretchFactor(1, 1)
        root_layout.addWidget(bottom_splitter, 1)
        self.setCentralWidget(root)

    def _top_status_bar(self) -> QFrame:
        """Create the top status bar with device, latency, and run state.

        @author Codex - created for the PySide6 mock console.
        """

        bar = QFrame()
        bar.setObjectName("topBar")
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(14)

        app_label = QLabel(APP_NAME)
        app_label.setObjectName("appTitle")
        layout.addWidget(app_label)
        layout.addStretch(1)

        self.mode_label = self._status_label("Mode: MOCK")
        self.fps_label = self._status_label("FPS: --")
        self.device_label = self._status_label("Input: USB Audio CODEC")
        self.sample_label = self._status_label(f"Sample rate: {SAMPLE_RATE} Hz")
        self.buffer_label = self._status_label(f"Buffer: {BUFFER_SIZE}")
        self.latency_label = self._status_label("Latency: -- ms")
        for label in [
            self.mode_label,
            self.fps_label,
            self.device_label,
            self.sample_label,
            self.buffer_label,
            self.latency_label,
        ]:
            layout.addWidget(label)

        self.start_button = QPushButton("Stop Simulation")
        self.start_button.setObjectName("primaryButton")
        layout.addWidget(self.start_button)
        return bar

    def _status_label(self, text: str) -> QLabel:
        """Create a compact status label for the top bar.

        @author Codex - created for the PySide6 mock console.
        """

        label = QLabel(text)
        label.setObjectName("statusPill")
        return label

    def _apply_style(self) -> None:
        """Apply the dark dashboard stylesheet.

        The style is local to this prototype so it does not impose a theme on
        future non-Qt interfaces.

        @author Codex - created for the PySide6 mock console.
        """

        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #0a0f17;
                color: #d8e2ef;
                font-family: Inter, Segoe UI, Arial, sans-serif;
                font-size: 12px;
            }
            #topBar, #panel {
                background: #111824;
                border: 1px solid #243043;
                border-radius: 8px;
            }
            #appTitle {
                color: #f8fafc;
                font-size: 18px;
                font-weight: 800;
            }
            #panelTitle {
                color: #f8fafc;
                font-size: 16px;
                font-weight: 800;
            }
            #sectionTitle {
                color: #c7d2fe;
                font-weight: 800;
            }
            #statusPill {
                background: #162235;
                border: 1px solid #29384f;
                border-radius: 6px;
                padding: 5px 8px;
                color: #b8c7dc;
            }
            #metricCard {
                background: #0d1420;
                border: 1px solid #233044;
                border-radius: 7px;
            }
            #metricTitle, #controlLabel {
                color: #8fa3bd;
                font-size: 11px;
                font-weight: 700;
            }
            #metricValue {
                color: #f8fafc;
                font-size: 17px;
                font-weight: 800;
            }
            QComboBox, QTextEdit, QTableWidget {
                background: #0d1420;
                border: 1px solid #25344a;
                border-radius: 6px;
                color: #d8e2ef;
                padding: 6px;
            }
            QComboBox::drop-down {
                border: 0;
                width: 22px;
            }
            QPushButton {
                background: #172236;
                border: 1px solid #2b3c55;
                border-radius: 6px;
                color: #d8e2ef;
                padding: 7px 9px;
                font-weight: 700;
            }
            QPushButton:hover {
                background: #20304a;
            }
            QPushButton:checked {
                background: #134e4a;
                border-color: #21d4fd;
                color: #f8fafc;
            }
            #primaryButton {
                background: #165f46;
                border-color: #24d18f;
                color: #f8fafc;
            }
            #segmentButton {
                padding: 6px 6px;
                font-size: 11px;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: #25344a;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 16px;
                margin: -5px 0;
                background: #21d4fd;
                border-radius: 8px;
            }
            #sliderValue {
                color: #f8fafc;
                font-weight: 800;
            }
            QHeaderView::section {
                background: #172236;
                color: #cbd5e1;
                border: 0;
                padding: 5px;
                font-weight: 800;
            }
            QTableWidget {
                gridline-color: #25344a;
            }
            #eventLog {
                color: #b8c7dc;
                font-family: JetBrains Mono, Consolas, monospace;
                font-size: 11px;
            }
            QSplitter::handle {
                background: #0a0f17;
            }
            """
        )

    def _connect_signals(self) -> None:
        """Connect panel actions to window-level use case operations.

        @author Codex - created for the PySide6 mock console.
        """

        self.control_panel.settingsChanged.connect(self._on_settings_changed)
        self.control_panel.actionTriggered.connect(self._on_control_action)
        self.start_button.clicked.connect(self._toggle_simulation)

    def _install_shortcuts(self) -> None:
        """Install window shortcuts for full-screen toggling.

        The shortcut is a desktop affordance and does not change the visible
        product surface requested for the mock dashboard.

        @author Codex - created for the PySide6 mock console.
        """

        action = QAction(self)
        action.setShortcut(QKeySequence("F11"))
        action.triggered.connect(self._toggle_fullscreen)
        self.addAction(action)

    def _on_settings_changed(self, settings: dict[str, Any]) -> None:
        """Accept a fresh control-panel settings snapshot.

        @author Codex - created for the PySide6 mock console.
        """

        settings["mock_error"] = self.mock_error
        previous_device = self.current_settings.get("input_device")
        previous_mode = self.current_settings.get("pitch_mode")
        previous_threshold = self.current_settings.get("rms_threshold")
        self.current_settings = settings
        self.device_label.setText(f"Input: {settings['input_device']}")

        if previous_device and previous_device != settings["input_device"]:
            self.event_log.add_message(f"Mock device selected: {settings['input_device']}")
        if previous_mode and previous_mode != settings["pitch_mode"]:
            self.event_log.add_message(f"Pitch mode changed: {settings['pitch_mode']}")
        if previous_threshold is not None and abs(previous_threshold - settings["rms_threshold"]) > 1e-9:
            self.event_log.add_message(f"Noise threshold changed: {settings['rms_threshold']:.2f}")

    def _on_control_action(self, action: str) -> None:
        """Handle non-continuous control-panel commands.

        Commands are explicit because these buttons represent future use cases
        that will eventually become real operations.

        @author Codex - created for the PySide6 mock console.
        """

        if action == "calibrate":
            self.control_panel.set_calibrated_threshold()
            self.event_log.add_message("Calibration complete")
        elif action == "freeze":
            self.frozen = not self.frozen
            self.event_log.add_message("Frame frozen" if self.frozen else "Frame unfrozen")
        elif action == "reset_score":
            self.generator.reset_score()
            self.event_log.add_message("Score reset")
        elif action == "toggle_error":
            self.mock_error = not self.mock_error
            self.current_settings["mock_error"] = self.mock_error
            self.event_log.add_message("Mock error enabled" if self.mock_error else "Mock error disabled")
        elif action == "export_screenshot":
            self.event_log.add_message("Export screenshot placeholder invoked")

    def _toggle_simulation(self) -> None:
        """Start or stop the QTimer-backed mock simulation.

        Stopping does not release any device because the prototype has no real
        microphone binding by design.

        @author Codex - created for the PySide6 mock console.
        """

        self.running = not self.running
        if self.running:
            self.generator.reset_clock()
            self.timer.start()
            self.start_button.setText("Stop Simulation")
            self.event_log.add_message("Simulation started")
        else:
            self.timer.stop()
            self.start_button.setText("Start Simulation")
            self.fps_label.setText("FPS: 0")
            self.event_log.add_message("Simulation stopped")

    def _toggle_fullscreen(self) -> None:
        """Toggle full-screen mode for dashboard review.

        @author Codex - created for the PySide6 mock console.
        """

        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()

    def _on_timer(self) -> None:
        """Generate and render one mock frame.

        This is the only real-time loop in the prototype, using ``QTimer`` as
        requested to demonstrate responsive Qt/PyQtGraph updates.

        @author Codex - created for the PySide6 mock console.
        """

        if self.frozen:
            return

        frame = self.generator.generate_frame(self.current_settings)
        self.waveform_plot.update_frame(frame)
        self.spectrum_plot.update_frame(frame)
        self.chroma_plot.update_frame(frame)
        self.analysis_panel.update_frame(frame)
        self._update_status(frame)
        self._log_frame_events(frame)

    def _update_status(self, frame: FrameData) -> None:
        """Update top-bar FPS and latency labels.

        @author Codex - created for the PySide6 mock console.
        """

        now = time.perf_counter()
        dt = now - self.last_frame_time
        self.last_frame_time = now
        if dt > 0:
            self.fps_samples.append(1.0 / dt)
        fps = sum(self.fps_samples) / max(len(self.fps_samples), 1)
        self.fps_label.setText(f"FPS: {fps:.0f}")
        self.latency_label.setText(f"Latency: {frame.latency_ms:.1f} ms")

    def _log_frame_events(self, frame: FrameData) -> None:
        """Emit high-signal simulated analysis events.

        The event log is throttled by state changes so it remains readable while
        the plots update at real-time cadence.

        @author Codex - created for the PySide6 mock console.
        """

        if frame.harmonic_lock and not self.last_harmonic_lock:
            self.event_log.add_message("Harmonic lock detected")
            self.event_log.add_message(f"Dominant peak chose {frame.dominant_note}")
            self.event_log.add_message(f"Fundamental estimator corrected to {frame.likely_fundamental_note}")
        self.last_harmonic_lock = frame.harmonic_lock

        if frame.match_result != self.last_match_result:
            if frame.match_result == "HIT":
                self.event_log.add_message(f"Target {frame.target_note} matched")
            elif frame.match_result == "MISS":
                self.event_log.add_message("Note missed")
            elif frame.match_result == "TOO QUIET":
                self.event_log.add_message("Input below RMS threshold")
            self.last_match_result = frame.match_result


def run_self_test() -> int:
    """Instantiate core objects and generate one frame for CI-style checks.

    This optional path validates construction without entering the GUI event
    loop, which is useful in headless development environments.

    @author Codex - created for the PySide6 mock console.
    """

    app = QApplication.instance() or QApplication(["audio-lab-mock", "-platform", "offscreen"])
    window = AudioLabMockWindow()
    frame = window.generator.generate_frame(window.current_settings)
    window.waveform_plot.update_frame(frame)
    window.spectrum_plot.update_frame(frame)
    window.chroma_plot.update_frame(frame)
    window.analysis_panel.update_frame(frame)
    window.close()
    app.processEvents()
    return 0


def main(argv: list[str] | None = None) -> int:
    """Run the mocked desktop dashboard.

    The public entry point exists so ``python -m interfaces.throwaway.audio_lab_mock``
    starts the full mock console without exposing Qt setup to callers.

    @author Codex - created for the PySide6 mock console.
    """

    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--self-test", action="store_true", help="construct the window and exit without showing it")
    args = parser.parse_args(argv)

    if args.self_test:
        return run_self_test()

    app = QApplication(sys.argv)
    pg.setConfigOptions(antialias=True)
    window = AudioLabMockWindow()
    window.showMaximized()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
