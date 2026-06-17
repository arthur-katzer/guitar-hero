"""Audio analysis helpers for the Guitar Hero prototype."""

from .chords import ChordResult, chroma_vector, detect_chord
from .dsp import DetectionResult, FrequencyPeak, analyze_pitch, analyze_windows, spectrum_peaks
from .io import AudioLoadError, load_audio

__all__ = [
    "AudioLoadError",
    "ChordResult",
    "DetectionResult",
    "FrequencyPeak",
    "analyze_pitch",
    "analyze_windows",
    "chroma_vector",
    "detect_chord",
    "load_audio",
    "spectrum_peaks",
]
