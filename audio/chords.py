"""Offline chord detection using chroma features and template matching."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Iterable

import numpy as np

from audio.dsp import NOTE_NAMES

CHORD_TEMPLATES = {
    "maj": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0],
    "min": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 0],
    "dim": [1, 0, 0, 1, 0, 0, 1, 0, 0, 0, 0, 0],
    "aug": [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
    "7": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 1, 0],
    "maj7": [1, 0, 0, 0, 1, 0, 0, 1, 0, 0, 0, 1],
    "min7": [1, 0, 0, 1, 0, 0, 0, 1, 0, 0, 1, 0],
    "sus4": [1, 0, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0],
    "sus2": [1, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0],
    "5": [1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0, 0],
}


@dataclass(frozen=True)
class ChordResult:
    start_time: float
    end_time: float
    chord_name: str
    root: str | None
    chord_type: str | None
    confidence: float
    chroma: list[float]
    rms: float

    def to_dict(self) -> dict:
        return asdict(self)


def detect_chord(
    samples: np.ndarray | Iterable[float],
    sample_rate: int,
    *,
    start_time: float = 0.0,
    noise_threshold: float = 0.01,
    min_frequency: float = 65.0,
    max_frequency: float = 2000.0,
    fft_size: int = 65536,
) -> ChordResult:
    mono = _to_mono_float(samples)
    duration = len(mono) / float(sample_rate) if sample_rate else 0.0
    window_rms = _rms(mono)

    if len(mono) == 0 or sample_rate <= 0 or window_rms < noise_threshold:
        return ChordResult(
            start_time=float(start_time),
            end_time=float(start_time + duration),
            chord_name="Silence",
            root=None,
            chord_type=None,
            confidence=0.0,
            chroma=[0.0] * 12,
            rms=window_rms,
        )

    chroma = chroma_vector(
        mono,
        sample_rate,
        min_frequency=min_frequency,
        max_frequency=max_frequency,
        fft_size=fft_size,
    )
    if not np.any(chroma):
        return ChordResult(
            start_time=float(start_time),
            end_time=float(start_time + duration),
            chord_name="Silence",
            root=None,
            chord_type=None,
            confidence=0.0,
            chroma=chroma.tolist(),
            rms=window_rms,
        )

    best_root = 0
    best_type = "maj"
    best_score = -1.0
    for root in range(12):
        shifted = np.roll(chroma, -root)
        for chord_type, template_values in CHORD_TEMPLATES.items():
            template = np.asarray(template_values, dtype=np.float64)
            template = template / (np.linalg.norm(template) + 1e-12)
            score = float(np.dot(shifted, template))
            if score > best_score:
                best_root = root
                best_type = chord_type
                best_score = score

    root_name = NOTE_NAMES[best_root]
    return ChordResult(
        start_time=float(start_time),
        end_time=float(start_time + duration),
        chord_name=f"{root_name} {best_type}",
        root=root_name,
        chord_type=best_type,
        confidence=max(0.0, min(1.0, best_score)),
        chroma=chroma.tolist(),
        rms=window_rms,
    )


def chroma_vector(
    samples: np.ndarray | Iterable[float],
    sample_rate: int,
    *,
    min_frequency: float = 65.0,
    max_frequency: float = 2000.0,
    fft_size: int = 65536,
) -> np.ndarray:
    mono = _to_mono_float(samples)
    if len(mono) == 0 or sample_rate <= 0:
        return np.zeros(12, dtype=np.float64)

    fft_size = max(fft_size, 1 << (len(mono) - 1).bit_length())
    windowed = mono * np.hanning(len(mono))
    magnitude = np.abs(np.fft.rfft(windowed, n=fft_size))
    freqs = np.fft.rfftfreq(fft_size, 1.0 / sample_rate)

    chroma = np.zeros(12, dtype=np.float64)
    mask = (freqs >= min_frequency) & (freqs <= max_frequency)
    for freq, mag in zip(freqs[mask], magnitude[mask]):
        if mag <= 0 or freq <= 0:
            continue
        midi_float = 69.0 + 12.0 * math.log2(float(freq) / 440.0)
        nearest = round(midi_float)
        pitch_class = int(nearest) % 12
        distance = abs(midi_float - nearest)
        weight = max(0.0, 1.0 - 2.0 * distance)
        chroma[pitch_class] += float(mag) * weight

    norm = np.linalg.norm(chroma)
    if norm > 0:
        chroma = chroma / norm
    chroma = chroma**2
    norm = np.linalg.norm(chroma)
    if norm > 0:
        chroma = chroma / norm
    return chroma


def _to_mono_float(samples: np.ndarray | Iterable[float]) -> np.ndarray:
    array = np.asarray(samples)
    if array.ndim == 2:
        array = np.mean(array, axis=1)
    return np.nan_to_num(array.astype(np.float32), copy=False)


def _rms(samples: np.ndarray) -> float:
    if len(samples) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(samples, dtype=np.float64))))
