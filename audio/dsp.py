"""
Pure DSP helpers for offline note detection.

The functions in this module do not read files, touch microphones, or draw UI.
They take numpy arrays and return structured results so the learning lab, tests,
and future game integration can share the same detection code.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable

import numpy as np

NOTE_NAMES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

DEFAULT_MIN_FREQUENCY = 70.0
DEFAULT_MAX_FREQUENCY = 1500.0
DEFAULT_NOISE_THRESHOLD = 0.01
DEFAULT_FFT_SIZE = 16384
DEFAULT_HPS_HARMONICS = 4


@dataclass(frozen=True)
class FrequencyPeak:
    """One visible peak in an FFT magnitude spectrum."""

    frequency_hz: float
    relative_magnitude: float
    note_name: str
    midi: int | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DetectionResult:
    """One analyzed audio window."""

    start_time: float
    end_time: float
    note_name: str
    midi: int | None
    frequency_hz: float
    cents: float
    confidence: float
    rms: float
    peak_frequency_hz: float
    hps_frequency_hz: float

    def to_dict(self) -> dict:
        return asdict(self)


def rms(samples: np.ndarray) -> float:
    """Return root-mean-square volume for one audio window."""
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))


def midi_to_note_name(midi_note: int) -> str:
    octave = midi_note // 12 - 1
    return f"{NOTE_NAMES[midi_note % 12]}{octave}"


def midi_to_frequency(midi_note: int) -> float:
    return float(440.0 * (2.0 ** ((midi_note - 69) / 12.0)))


def frequency_to_midi(frequency_hz: float) -> tuple[int, float]:
    """Return nearest MIDI note and cents deviation for a frequency."""
    if frequency_hz <= 0:
        raise ValueError("frequency_hz must be positive")
    midi_float = 69.0 + 12.0 * math.log2(frequency_hz / 440.0)
    midi_note = int(round(midi_float))
    cents = (midi_float - midi_note) * 100.0
    return midi_note, float(cents)


def analyze_pitch(
    samples: np.ndarray,
    sample_rate: int,
    *,
    start_time: float = 0.0,
    noise_threshold: float = DEFAULT_NOISE_THRESHOLD,
    min_frequency: float = DEFAULT_MIN_FREQUENCY,
    max_frequency: float = DEFAULT_MAX_FREQUENCY,
    fft_size: int = DEFAULT_FFT_SIZE,
    hps_harmonics: int = DEFAULT_HPS_HARMONICS,
) -> DetectionResult:
    """
    Detect the dominant single note in one audio window.

    The primary frequency estimate is the strongest FFT peak. A Harmonic Product
    Spectrum estimate is also computed and returned for inspection; future
    versions can use it more aggressively once real guitar recordings are
    calibrated.
    """
    mono = _to_mono_float(samples)
    duration = len(mono) / float(sample_rate) if sample_rate else 0.0
    window_rms = rms(mono)

    if len(mono) == 0 or sample_rate <= 0 or window_rms < noise_threshold:
        return _silence(start_time, start_time + duration, window_rms)

    fft_size = _valid_fft_size(fft_size, len(mono))
    windowed = mono * np.hanning(len(mono))
    spectrum = np.fft.rfft(windowed, n=fft_size)
    magnitude = np.abs(spectrum)
    freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)

    mask = (freqs >= min_frequency) & (freqs <= max_frequency)
    if not np.any(mask):
        return _silence(start_time, start_time + duration, window_rms)

    masked_magnitude = np.where(mask, magnitude, 0.0)
    peak_idx = int(np.argmax(masked_magnitude))
    peak_frequency = float(freqs[peak_idx])

    hps_frequency = _harmonic_product_frequency(
        magnitude,
        freqs,
        mask,
        hps_harmonics,
    )

    if peak_frequency <= 0:
        return _silence(start_time, start_time + duration, window_rms)

    midi_note, cents = frequency_to_midi(peak_frequency)
    if not 0 <= midi_note < 128:
        return _silence(start_time, start_time + duration, window_rms)

    confidence = _peak_confidence(masked_magnitude, peak_idx)
    return DetectionResult(
        start_time=float(start_time),
        end_time=float(start_time + duration),
        note_name=midi_to_note_name(midi_note),
        midi=midi_note,
        frequency_hz=peak_frequency,
        cents=cents,
        confidence=confidence,
        rms=window_rms,
        peak_frequency_hz=peak_frequency,
        hps_frequency_hz=hps_frequency,
    )


def analyze_windows(
    samples: np.ndarray,
    sample_rate: int,
    *,
    window_ms: float = 100.0,
    hop_ms: float = 50.0,
    noise_threshold: float = DEFAULT_NOISE_THRESHOLD,
    min_frequency: float = DEFAULT_MIN_FREQUENCY,
    max_frequency: float = DEFAULT_MAX_FREQUENCY,
    fft_size: int = DEFAULT_FFT_SIZE,
) -> list[DetectionResult]:
    """Analyze an entire audio array as overlapping windows."""
    mono = _to_mono_float(samples)
    if len(mono) == 0:
        return []

    window_size = max(1, int(sample_rate * window_ms / 1000.0))
    hop_size = max(1, int(sample_rate * hop_ms / 1000.0))
    results: list[DetectionResult] = []

    for start in range(0, len(mono), hop_size):
        chunk = mono[start : start + window_size]
        if len(chunk) < window_size:
            chunk = np.pad(chunk, (0, window_size - len(chunk)))
        results.append(
            analyze_pitch(
                chunk,
                sample_rate,
                start_time=start / float(sample_rate),
                noise_threshold=noise_threshold,
                min_frequency=min_frequency,
                max_frequency=max_frequency,
                fft_size=fft_size,
            )
        )
        if start + window_size >= len(mono):
            break

    return results


def spectrum_peaks(
    samples: np.ndarray,
    sample_rate: int,
    *,
    count: int = 8,
    min_frequency: float = DEFAULT_MIN_FREQUENCY,
    max_frequency: float = DEFAULT_MAX_FREQUENCY,
    fft_size: int = DEFAULT_FFT_SIZE,
) -> list[FrequencyPeak]:
    """Return the strongest separate FFT peaks in one audio window."""
    mono = _to_mono_float(samples)
    if len(mono) == 0 or sample_rate <= 0 or count <= 0:
        return []

    fft_size = _valid_fft_size(fft_size, len(mono))
    windowed = mono * np.hanning(len(mono))
    magnitude = np.abs(np.fft.rfft(windowed, n=fft_size))
    freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)
    mask = (freqs >= min_frequency) & (freqs <= max_frequency)
    masked = np.where(mask, magnitude, 0.0)

    if np.max(masked) <= 0:
        return []

    peaks: list[FrequencyPeak] = []
    working = masked.copy()
    max_magnitude = float(np.max(working))
    # Suppress nearby bins by frequency, not by a fixed bin count. Very long
    # windows have tiny FFT bin spacing, so fixed-bin suppression would report
    # the same broadened frequency peak several times.
    suppression_hz = 10.0

    for _ in range(count):
        idx = int(np.argmax(working))
        peak_magnitude = float(working[idx])
        if peak_magnitude <= 0:
            break

        frequency = float(freqs[idx])
        midi_note, _ = frequency_to_midi(frequency)
        peaks.append(
            FrequencyPeak(
                frequency_hz=frequency,
                relative_magnitude=peak_magnitude / max_magnitude,
                note_name=midi_to_note_name(midi_note) if 0 <= midi_note < 128 else "?",
                midi=midi_note if 0 <= midi_note < 128 else None,
            )
        )

        nearby = np.abs(freqs - frequency) <= suppression_hz
        working[nearby] = 0.0

    return peaks


def summarize_audio(samples: np.ndarray, sample_rate: int) -> dict:
    mono = _to_mono_float(samples)
    return {
        "sample_rate": sample_rate,
        "samples": int(len(mono)),
        "duration_seconds": len(mono) / float(sample_rate) if sample_rate else 0.0,
        "rms": rms(mono),
    }


def _to_mono_float(samples: np.ndarray | Iterable[float]) -> np.ndarray:
    array = np.asarray(samples)
    if array.ndim == 2:
        array = np.mean(array, axis=1)
    if array.dtype.kind in {"i", "u"}:
        max_value = np.iinfo(array.dtype).max
        array = array.astype(np.float32) / float(max_value)
    else:
        array = array.astype(np.float32)
    return np.nan_to_num(array, copy=False)


def _valid_fft_size(requested_size: int, sample_count: int) -> int:
    minimum = max(2, sample_count)
    if requested_size >= minimum:
        return int(requested_size)
    return 1 << (minimum - 1).bit_length()


def _silence(start_time: float, end_time: float, window_rms: float) -> DetectionResult:
    return DetectionResult(
        start_time=float(start_time),
        end_time=float(end_time),
        note_name="Silence",
        midi=None,
        frequency_hz=0.0,
        cents=0.0,
        confidence=0.0,
        rms=float(window_rms),
        peak_frequency_hz=0.0,
        hps_frequency_hz=0.0,
    )


def _peak_confidence(magnitude: np.ndarray, peak_idx: int) -> float:
    peak = float(magnitude[peak_idx])
    if peak <= 0:
        return 0.0

    # Confidence here means "the winning pitch peak is clearly stronger than
    # nearby alternatives." It is not a probability that the musical note is
    # correct. Ignore a small neighborhood around the peak so the same broadened
    # lobe does not count as its own competitor.
    competitor_magnitude = magnitude.copy()
    neighborhood = 4
    start = max(0, peak_idx - neighborhood)
    end = min(len(competitor_magnitude), peak_idx + neighborhood + 1)
    competitor_magnitude[start:end] = 0.0

    second_peak = float(np.max(competitor_magnitude))
    nonzero = magnitude[magnitude > 0]
    floor = float(np.median(nonzero)) if len(nonzero) else 0.0

    competitor_score = peak / (peak + second_peak + 1e-12)
    floor_score = peak / (peak + floor + 1e-12)
    confidence = 0.8 * competitor_score + 0.2 * floor_score
    return float(max(0.0, min(1.0, confidence)))


def _harmonic_product_frequency(
    magnitude: np.ndarray,
    freqs: np.ndarray,
    mask: np.ndarray,
    harmonics: int,
) -> float:
    if harmonics <= 1:
        hps = np.where(mask, magnitude, 0.0)
    else:
        normalized = magnitude / (np.max(magnitude) + 1e-12)
        hps = normalized.copy()
        for harmonic in range(2, harmonics + 1):
            decimated = normalized[::harmonic]
            hps[: len(decimated)] *= decimated
            hps[len(decimated) :] = 0.0
        hps = np.where(mask, hps, 0.0)

    peak_idx = int(np.argmax(hps))
    if hps[peak_idx] <= 0:
        return 0.0
    return float(freqs[peak_idx])
