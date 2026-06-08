"""Offline audio analysis tools for the Guitar Hero prototype."""

from .chords import ChordResult, chroma_vector, detect_chord
from .dsp import DetectionResult, FrequencyPeak, analyze_pitch, analyze_windows, spectrum_peaks
from .io import AudioLoadError, load_audio
from .matching import MatchResult, MatchSummary, match_detections_to_chart

__all__ = [
    "AudioLoadError",
    "ChordResult",
    "DetectionResult",
    "FrequencyPeak",
    "MatchResult",
    "MatchSummary",
    "analyze_pitch",
    "analyze_windows",
    "chroma_vector",
    "detect_chord",
    "load_audio",
    "match_detections_to_chart",
    "spectrum_peaks",
]
