"""Offline matching between detected audio notes and MIDI chart events."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Iterable

from audio.dsp import DetectionResult


@dataclass(frozen=True)
class MatchResult:
    chart_time: float
    expected_midi: int
    expected_note: str
    detected_time: float | None
    detected_midi: int | None
    detected_note: str | None
    time_delta: float | None
    confidence: float
    status: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MatchSummary:
    total_events: int
    hits: int
    misses: int
    accuracy: float
    hit_window: float
    midi_tolerance: int
    min_confidence: float
    results: list[MatchResult]

    def to_dict(self) -> dict:
        data = asdict(self)
        data["results"] = [result.to_dict() for result in self.results]
        return data


def match_detections_to_chart(
    chart_events: Iterable[dict],
    detections: Iterable[DetectionResult],
    *,
    hit_window: float = 0.25,
    midi_tolerance: int = 0,
    min_confidence: float = 0.5,
) -> MatchSummary:
    """Match each chart event against nearby detected audio windows."""
    events = sorted(_valid_chart_events(chart_events), key=lambda event: event["time"])
    usable_detections = [
        detection
        for detection in detections
        if detection.midi is not None and detection.confidence >= min_confidence
    ]
    used_detection_indexes: set[int] = set()
    results: list[MatchResult] = []

    for event in events:
        expected_midi = int(event["midi"])
        expected_note = str(event.get("note", expected_midi))
        best_index: int | None = None
        best_delta: float | None = None

        for idx, detection in enumerate(usable_detections):
            if idx in used_detection_indexes:
                continue
            if detection.midi is None:
                continue
            if abs(detection.midi - expected_midi) > midi_tolerance:
                continue
            detected_time = _detection_center(detection)
            delta = detected_time - float(event["time"])
            if abs(delta) > hit_window:
                continue
            if best_delta is None or abs(delta) < abs(best_delta):
                best_index = idx
                best_delta = delta

        if best_index is None or best_delta is None:
            results.append(
                MatchResult(
                    chart_time=float(event["time"]),
                    expected_midi=expected_midi,
                    expected_note=expected_note,
                    detected_time=None,
                    detected_midi=None,
                    detected_note=None,
                    time_delta=None,
                    confidence=0.0,
                    status="miss",
                )
            )
            continue

        used_detection_indexes.add(best_index)
        detection = usable_detections[best_index]
        results.append(
            MatchResult(
                chart_time=float(event["time"]),
                expected_midi=expected_midi,
                expected_note=expected_note,
                detected_time=_detection_center(detection),
                detected_midi=detection.midi,
                detected_note=detection.note_name,
                time_delta=best_delta,
                confidence=detection.confidence,
                status="hit",
            )
        )

    hits = sum(1 for result in results if result.status == "hit")
    total = len(results)
    misses = total - hits
    return MatchSummary(
        total_events=total,
        hits=hits,
        misses=misses,
        accuracy=(hits / total) if total else 0.0,
        hit_window=hit_window,
        midi_tolerance=midi_tolerance,
        min_confidence=min_confidence,
        results=results,
    )


def _valid_chart_events(chart_events: Iterable[dict]) -> list[dict]:
    return [
        event
        for event in chart_events
        if "time" in event and "midi" in event
    ]


def _detection_center(detection: DetectionResult) -> float:
    return (detection.start_time + detection.end_time) / 2.0
