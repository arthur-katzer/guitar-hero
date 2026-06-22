"""Shared live-audio pitch and pluck-event analysis.

This module owns the live-audio boundary for use cases that need guitar note
events. It keeps device access and FFT pitch policy independent from Qt so
Sandbox and Learn can change their widgets without rewriting detector behavior.
"""

from __future__ import annotations

import math
import queue
from dataclasses import dataclass
from typing import Any

import numpy as np

try:
    import sounddevice as sd
except ImportError:  # pragma: no cover - dependency diagnostics are runtime UI state.
    sd = None


DEFAULT_SAMPLE_RATE = 48_000
DEFAULT_CHANNELS = 1
DEFAULT_BLOCK_MS = 50
MIN_HZ = 60.0
MAX_HZ = 1_200.0
NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
LOW_OPEN_STRING_NAMES = ("E2", "A2")
OPEN_STRING_CANDIDATES: tuple[tuple[str, int, float], ...] = (
    ("E2", 40, 82.41),
    ("A2", 45, 110.00),
    ("D3", 50, 146.83),
    ("G3", 55, 196.00),
    ("B3", 59, 246.94),
    ("E4", 64, 329.63),
)


@dataclass(frozen=True)
class AudioDevice:
    """Input device that can be opened by the sandbox.

    The UI needs stable labels and indexes, while the stream opener needs the
    PortAudio index. Keeping both in one value avoids making widgets query
    ``sounddevice`` directly.

    @author Codex - created live sandbox audio boundary.
    """

    index: int
    name: str
    input_channels: int
    default_sample_rate: int


@dataclass(frozen=True)
class SpectrumPeak:
    """One ranked FFT peak shown by the sandbox chart.

    @author Codex - created live sandbox audio boundary.
    """

    frequency_hz: float
    magnitude: float
    relative_percent: float
    midi: int
    note: str
    harmonic_relationship: str


@dataclass(frozen=True)
class PitchFrame:
    """Complete detector snapshot for one live audio buffer.

    @author Codex - created live sandbox audio boundary.
    """

    rms: float
    dominant_peak: SpectrumPeak | None
    likely_fundamental: SpectrumPeak | None
    confidence: float
    harmonic_lock: bool
    reason: str
    display_stable: bool
    peaks: tuple[SpectrumPeak, ...]
    spectrum_frequencies: np.ndarray
    spectrum_magnitudes: np.ndarray


@dataclass(frozen=True)
class OpenStringHarmonicMatch:
    """One observed peak supporting an open-string harmonic family.

    The sandbox needs to show why a string was considered without promoting a
    shared harmonic to a played string. ``overlap_notes`` records open strings
    that can explain the same peak with stronger context, including active
    lower families and direct higher-string fundamentals.

    @author Codex - added open-string family diagnostic.
    """

    harmonic: int
    expected_hz: float
    observed_hz: float
    strength_percent: float
    overlap_notes: tuple[str, ...]
    evidence_level: str = "present"

    def relative_strength_is_present(self) -> bool:
        """Return whether this match is strong enough for normal evidence.

        Weak low-string anchors help E2/A2 stay visible, but co-present overlap
        needs normally visible support before an overlapped fundamental can be
        treated as a real played string.

        @author Codex - added co-present overlap handling.
        """

        return self.evidence_level == "present"


@dataclass(frozen=True)
class OpenStringFamilyEvidence:
    """Evidence summary for one standard-tuning open string.

    This is diagnostic policy, not chord naming. It answers whether the pluck
    capture window contains harmonic evidence for one open-string family while
    preserving uncertainty and harmonic overlap.

    @author Codex - added open-string family diagnostic.
    """

    string_name: str
    midi: int
    frequency_hz: float
    score_percent: float
    status: str
    matches: tuple[OpenStringHarmonicMatch, ...]
    debug_text: str


@dataclass(frozen=True)
class OpenStringFamilyReport:
    """Diagnostic report for all standard open guitar strings.

    The report keeps guitar-order rows for the UI and a ranked view for future
    debugging without changing the single-note pluck contract.

    @author Codex - added open-string family diagnostic.
    """

    families: tuple[OpenStringFamilyEvidence, ...]
    ranked: tuple[OpenStringFamilyEvidence, ...]


def inactive_open_string_report() -> OpenStringFamilyReport:
    """Return a report with every open string marked inactive.

    Silence and no-peak captures still need a complete diagnostic table so the
    Sandbox UI does not have to invent default domain rows.

    @author Codex - added open-string family diagnostic.
    """

    families = tuple(
        OpenStringFamilyEvidence(
            string_name=name,
            midi=midi,
            frequency_hz=frequency,
            score_percent=0.0,
            status="inactive",
            matches=(),
            debug_text="no peaks in captured pluck window",
        )
        for name, midi, frequency in OPEN_STRING_CANDIDATES
    )
    return OpenStringFamilyReport(families=families, ranked=families)


@dataclass(frozen=True)
class DetectedPluck:
    """A note event classified from one physical pluck, not one FFT frame.

    The sandbox distinguishes live spectrum evidence from the musical event
    because harmonic strengths move during decay. This value is the stable
    pluck-level result the GUI can latch while the FFT remains live.

    @author Codex - added pluck-level note event model.
    """

    note_name: str
    midi: int
    frequency_hz: float
    confidence: float
    dominant_frequency_hz: float
    harmonic_matches: list[str]
    started_at: float
    ended_at: float | None
    reason: str
    open_string_families: OpenStringFamilyReport


@dataclass(frozen=True)
class FundamentalEstimate:
    """Pitch estimate chosen from visible FFT peaks.

    @author Codex - ported old harmonic-aware detector into sandbox boundary.
    """

    peak: SpectrumPeak
    confidence: float
    harmonic_multiples: tuple[int, ...]
    used_fallback: bool
    reason: str


@dataclass(frozen=True)
class _PluckEvidence:
    midi: int
    frequency_hz: float
    score: float
    harmonic_multiples: tuple[int, ...]
    frame_index: int


@dataclass
class _PluckCandidate:
    midi: int
    score: float = 0.0
    weighted_frequency: float = 0.0
    weight: float = 0.0
    harmonic_multiples: set[int] | None = None
    frame_indexes: set[int] | None = None

    def __post_init__(self) -> None:
        if self.harmonic_multiples is None:
            self.harmonic_multiples = set()
        if self.frame_indexes is None:
            self.frame_indexes = set()


class OpenStringFamilyDetector:
    """Score standard open-string families from one pluck capture window.

    Open-string evidence is intentionally separate from the note detector. A
    multi-string pluck can contain multiple valid harmonic families, while the
    existing pluck detector still emits one stable note for the legacy readout.

    @author Codex - added open-string family diagnostic.
    @author Codex - added cautious weak-anchor handling for low open strings.
    """

    MATCH_TOLERANCE = 0.035
    MIN_PEAK_PERCENT = 8.0
    WEAK_LOW_ANCHOR_PEAK_PERCENT = 4.0
    STRONG_SECOND_HARMONIC_PERCENT = 25.0
    ACTIVE_SCORE_THRESHOLD = 55.0
    UNCERTAIN_SCORE_THRESHOLD = 25.0

    def analyze_frames(self, frames: list[PitchFrame]) -> OpenStringFamilyReport:
        """Return evidence for each standard-tuning open string.

        The detector consumes the captured attack window because the business
        question is "which open strings have evidence in this pluck", not which
        note dominates one volatile FFT frame.

        @author Codex - added open-string family diagnostic.
        """

        if not any(frame.peaks for frame in frames):
            return inactive_open_string_report()

        families: list[OpenStringFamilyEvidence] = []
        stronger_active: list[OpenStringFamilyEvidence] = []
        for name, midi, frequency in OPEN_STRING_CANDIDATES:
            matches = self._matches_for_family(name, frequency, frames, stronger_active)
            evidence = self._evidence_for_family(name, midi, frequency, matches, stronger_active, frames)
            families.append(evidence)
            if evidence.status == "active":
                stronger_active.append(evidence)

        return OpenStringFamilyReport(
            families=tuple(families),
            ranked=tuple(sorted(families, key=lambda family: family.score_percent, reverse=True)),
        )

    def _matches_for_family(
        self,
        name: str,
        frequency_hz: float,
        frames: list[PitchFrame],
        stronger_active: list[OpenStringFamilyEvidence],
    ) -> tuple[OpenStringHarmonicMatch, ...]:
        matches: list[OpenStringHarmonicMatch] = []
        for harmonic in range(1, 7):
            expected_hz = frequency_hz * harmonic
            possible_matches = [
                peak
                for frame in frames
                for peak in frame.peaks
                if peak.relative_percent >= self._minimum_peak_percent(name, harmonic)
                and harmonic_error(frequency_hz, peak.frequency_hz, harmonic) <= self.MATCH_TOLERANCE
            ]
            if not possible_matches:
                continue
            peak = max(possible_matches, key=lambda candidate: candidate.relative_percent)
            overlap_notes = tuple(
                family.string_name
                for family in stronger_active
                if self._peak_matches_family(peak.frequency_hz, family.frequency_hz)
            ) + self._higher_fundamental_overlaps(name, frequency_hz, peak.frequency_hz)
            overlap_notes = tuple(dict.fromkeys(overlap_notes))
            matches.append(
                OpenStringHarmonicMatch(
                    harmonic=harmonic,
                    expected_hz=expected_hz,
                    observed_hz=peak.frequency_hz,
                    strength_percent=peak.relative_percent,
                    overlap_notes=overlap_notes,
                    evidence_level="weak" if peak.relative_percent < self.MIN_PEAK_PERCENT else "present",
                )
            )
        return tuple(matches)

    def _evidence_for_family(
        self,
        name: str,
        midi: int,
        frequency_hz: float,
        matches: tuple[OpenStringHarmonicMatch, ...],
        stronger_active: list[OpenStringFamilyEvidence],
        frames: list[PitchFrame],
    ) -> OpenStringFamilyEvidence:
        raw_score = self._raw_score(matches)
        lower_overlap_notes = {family.string_name for family in stronger_active}
        lower_independent_matches = tuple(
            match
            for match in matches
            if not lower_overlap_notes.intersection(match.overlap_notes)
        )
        co_present_anchor_matches = self._co_present_anchor_matches(
            matches,
            lower_independent_matches,
            lower_overlap_notes,
        )
        scoring_matches = tuple(dict.fromkeys(lower_independent_matches + co_present_anchor_matches))
        score_basis = self._raw_score(scoring_matches)
        active_anchor = self._has_active_anchor(scoring_matches)
        uncertain_anchor = self._has_uncertain_anchor(scoring_matches)
        has_lower_overlap = any(
            lower_overlap_notes.intersection(match.overlap_notes)
            for match in matches
        )
        has_higher_fundamental_overlap = any(
            any(note not in lower_overlap_notes for note in match.overlap_notes)
            for match in matches
        )
        lower_overlap_heavy = (
            raw_score >= 20.0
            and has_lower_overlap
            and (
                any(match.harmonic == 1 for match in matches)
                or len(matches) >= 2
            )
            and score_basis < max(20.0, raw_score * 0.45)
            and not co_present_anchor_matches
        )
        subharmonic_hallucination = (
            raw_score >= 20.0
            and has_higher_fundamental_overlap
            and not active_anchor
            and len(matches) >= 2
        )

        if score_basis >= self.ACTIVE_SCORE_THRESHOLD and active_anchor:
            status = "active"
            score = score_basis
        elif lower_overlap_heavy or subharmonic_hallucination:
            status = "harmonic overlap"
            score = min(45.0, max(20.0, raw_score * 0.4))
        elif (
            score_basis >= self.UNCERTAIN_SCORE_THRESHOLD
            and uncertain_anchor
        ):
            status = "uncertain"
            score = score_basis
        else:
            status = "inactive"
            score = min(self.UNCERTAIN_SCORE_THRESHOLD - 1.0, score_basis)

        return OpenStringFamilyEvidence(
            string_name=name,
            midi=midi,
            frequency_hz=frequency_hz,
            score_percent=min(100.0, round(score, 1)),
            status=status,
            matches=matches,
            debug_text=self._debug_text(
                name,
                frequency_hz,
                frames,
                matches,
                scoring_matches,
                co_present_anchor_matches,
                status,
            ),
        )

    def _minimum_peak_percent(self, name: str, harmonic: int) -> float:
        if name in LOW_OPEN_STRING_NAMES and harmonic in {1, 2}:
            return self.WEAK_LOW_ANCHOR_PEAK_PERCENT
        return self.MIN_PEAK_PERCENT

    def _raw_score(self, matches: tuple[OpenStringHarmonicMatch, ...]) -> float:
        if not matches:
            return 0.0
        score = 0.0
        for match in matches:
            strength = min(match.strength_percent, 100.0) / 100.0
            if match.harmonic == 1:
                score += 50.0 * strength + 20.0
            elif match.harmonic == 2:
                score += 24.0 * strength + 8.0
            elif match.harmonic == 3:
                score += 16.0 * strength + 5.0
            elif match.harmonic == 4:
                score += 10.0 * strength + 3.0
            elif match.harmonic == 5:
                score += 5.0 * strength + 1.0
            else:
                score += 4.0 * strength + 1.0
        low_order_count = len({match.harmonic for match in matches if match.harmonic <= 4})
        if low_order_count >= 2:
            score += 8.0
        if low_order_count >= 3:
            score += 6.0
        if low_order_count >= 4:
            score += 4.0
        return min(100.0, score)

    def _peak_matches_family(self, peak_hz: float, family_frequency_hz: float) -> bool:
        for harmonic in range(1, 7):
            if harmonic_error(family_frequency_hz, peak_hz, harmonic) <= self.MATCH_TOLERANCE:
                return True
        return False

    def _higher_fundamental_overlaps(
        self,
        name: str,
        frequency_hz: float,
        peak_hz: float,
    ) -> tuple[str, ...]:
        return tuple(
            candidate_name
            for candidate_name, _midi, candidate_frequency in OPEN_STRING_CANDIDATES
            if candidate_name != name
            and candidate_frequency > frequency_hz
            and harmonic_error(candidate_frequency, peak_hz, 1) <= self.MATCH_TOLERANCE
        )

    def _has_active_anchor(self, matches: tuple[OpenStringHarmonicMatch, ...]) -> bool:
        has_fundamental = any(
            match.harmonic == 1
            and (
                match.evidence_level == "present"
                or any(other.harmonic in {2, 3, 4} for other in matches)
            )
            for match in matches
        )
        strong_second = any(
            match.harmonic == 2
            and match.strength_percent >= self.STRONG_SECOND_HARMONIC_PERCENT
            for match in matches
        )
        low_order_harmonics = {match.harmonic for match in matches if match.harmonic <= 4}
        return has_fundamental or (strong_second and len(low_order_harmonics) >= 2)

    def _has_uncertain_anchor(self, matches: tuple[OpenStringHarmonicMatch, ...]) -> bool:
        if any(match.harmonic in {1, 2} for match in matches):
            return True
        low_order_harmonics = {match.harmonic for match in matches if match.harmonic <= 4}
        return len(low_order_harmonics) >= 3 and min(low_order_harmonics, default=99) <= 3

    def _co_present_anchor_matches(
        self,
        matches: tuple[OpenStringHarmonicMatch, ...],
        lower_independent_matches: tuple[OpenStringHarmonicMatch, ...],
        lower_overlap_notes: set[str],
    ) -> tuple[OpenStringHarmonicMatch, ...]:
        if not lower_overlap_notes:
            return ()
        independent_low_support = [
            match
            for match in lower_independent_matches
            if 2 <= match.harmonic <= 4 and match.relative_strength_is_present()
        ]
        has_near_anchor_support = any(match.harmonic in {2, 3} for match in independent_low_support)
        has_multiple_low_support = len({match.harmonic for match in independent_low_support}) >= 2
        if not has_near_anchor_support and not has_multiple_low_support:
            return ()
        return tuple(
            match
            for match in matches
            if match.harmonic in {1, 2}
            and lower_overlap_notes.intersection(match.overlap_notes)
            and match.relative_strength_is_present()
        )

    def _debug_text(
        self,
        name: str,
        frequency_hz: float,
        frames: list[PitchFrame],
        matches: tuple[OpenStringHarmonicMatch, ...],
        scoring_matches: tuple[OpenStringHarmonicMatch, ...],
        co_present_anchor_matches: tuple[OpenStringHarmonicMatch, ...],
        status: str,
    ) -> str:
        if not matches:
            low_string_trace = self._low_string_trace(name, frequency_hz, frames)
            if low_string_trace:
                return f"no visible harmonics matched 1x-6x; {low_string_trace}"
            return "no visible harmonics matched 1x-6x"

        parts = [
            "matched harmonics: "
            + ", ".join(
                f"{match.harmonic}x={match.observed_hz:.0f} Hz"
                + (" weak" if match.evidence_level == "weak" else "")
                + (f" overlaps {'/'.join(match.overlap_notes)}" if match.overlap_notes else "")
                for match in matches
            )
        ]
        low_string_trace = self._low_string_trace(name, frequency_hz, frames)
        if low_string_trace:
            parts.append(low_string_trace)
        if co_present_anchor_matches:
            parts.append("overlapped 1x/2x retained because independent harmonics support co-present string")
        if not any(match.harmonic == 1 for match in scoring_matches):
            parts.append("independent fundamental weak/missing")
        if matches and not self._has_uncertain_anchor(scoring_matches):
            parts.append("no 1x/2x anchor; upper harmonics are diagnostic only")
        if status == "harmonic overlap":
            parts.append("evidence mostly explained by overlapping open-string families")
        return "; ".join(parts)

    def _low_string_trace(
        self,
        name: str,
        frequency_hz: float,
        frames: list[PitchFrame],
    ) -> str:
        if name not in LOW_OPEN_STRING_NAMES:
            return ""
        entries: list[str] = []
        for harmonic in range(1, 7):
            expected_hz = frequency_hz * harmonic
            possible_matches = [
                peak
                for frame in frames
                for peak in frame.peaks
                if harmonic_error(frequency_hz, peak.frequency_hz, harmonic) <= self.MATCH_TOLERANCE
            ]
            peak = max(possible_matches, key=lambda candidate: candidate.relative_percent, default=None)
            if peak is None or peak.relative_percent < self.WEAK_LOW_ANCHOR_PEAK_PERCENT:
                entries.append(f"{harmonic}x~{expected_hz:.0f}Hz missing")
            elif peak.relative_percent < self.MIN_PEAK_PERCENT:
                entries.append(f"{harmonic}x~{expected_hz:.0f}Hz weak {peak.relative_percent:.0f}%")
            else:
                entries.append(f"{harmonic}x~{expected_hz:.0f}Hz present {peak.relative_percent:.0f}%")
        return f"low-string trace: {', '.join(entries)}"


class PluckDetector:
    """Convert live FFT frames into stable pluck-level note events.

    The detector owns the state machine between frame analysis and interface
    readout. FFT frames remain volatile diagnostic evidence; a note event is
    emitted only after an attack window has enough evidence to choose the
    fundamental that best explains the observed harmonic series.

    @author Codex - added pluck-level detector between FFT frames and GUI.
    """

    IDLE = "IDLE"
    CAPTURING = "CAPTURING"
    LATCHED = "LATCHED"

    def __init__(
        self,
        *,
        attack_rms_threshold: float = 0.008,
        attack_rise_threshold: float = 0.003,
        release_rms_threshold: float = 0.004,
        capture_window_seconds: float = 0.16,
        release_window_seconds: float = 0.22,
    ):
        self.attack_rms_threshold = attack_rms_threshold
        self.attack_rise_threshold = attack_rise_threshold
        self.release_rms_threshold = release_rms_threshold
        self.capture_window_seconds = capture_window_seconds
        self.release_window_seconds = release_window_seconds
        self._open_string_detector = OpenStringFamilyDetector()
        self.reset()

    @property
    def state(self) -> str:
        """Return the current pluck state-machine state.

        @author Codex - added pluck-level detector between FFT frames and GUI.
        """

        return self._state

    @property
    def current_pluck(self) -> DetectedPluck | None:
        """Return the latched pluck event, if one is active.

        @author Codex - added pluck-level detector between FFT frames and GUI.
        """

        return self._current_pluck

    def reset(self) -> None:
        """Return the detector to silence-ready state.

        @author Codex - added pluck-level detector between FFT frames and GUI.
        """

        self._state = self.IDLE
        self._previous_rms = 0.0
        self._started_at = 0.0
        self._release_started_at: float | None = None
        self._captured_frames: list[PitchFrame] = []
        self._current_pluck: DetectedPluck | None = None

    def process_frame(self, frame: PitchFrame, now: float) -> DetectedPluck | None:
        """Consume one FFT frame and return a new pluck event when classified.

        Frames are intentionally not exposed as note changes. The GUI should
        call this for every live frame, update FFT widgets from the frame, and
        update the note display only when this method returns a new event.

        @author Codex - added pluck-level detector between FFT frames and GUI.
        """

        previous_rms = self._previous_rms
        rms_rise = frame.rms - previous_rms
        self._previous_rms = frame.rms

        if self._state == self.IDLE:
            if self._is_attack(frame.rms, previous_rms, rms_rise):
                self._begin_capture(frame, now)
            return None

        if self._state == self.CAPTURING:
            self._captured_frames.append(frame)
            if now - self._started_at >= self.capture_window_seconds:
                pluck = self._classify()
                self._state = self.LATCHED if pluck is not None else self.IDLE
                self._current_pluck = pluck
                self._release_started_at = None
                return pluck
            return None

        if self._state == self.LATCHED:
            if frame.rms <= self.release_rms_threshold:
                if self._release_started_at is None:
                    self._release_started_at = now
                elif now - self._release_started_at >= self.release_window_seconds:
                    self._state = self.IDLE
                    self._current_pluck = None
                    self._captured_frames = []
                    self._release_started_at = None
            else:
                self._release_started_at = None
            return None

        self._state = self.IDLE
        return None

    def _is_attack(self, rms: float, previous_rms: float, rms_rise: float) -> bool:
        return rms >= self.attack_rms_threshold and (
            previous_rms < self.attack_rms_threshold or rms_rise >= self.attack_rise_threshold
        )

    def _begin_capture(self, frame: PitchFrame, now: float) -> None:
        self._state = self.CAPTURING
        self._started_at = now
        self._captured_frames = [frame]
        self._current_pluck = None
        self._release_started_at = None

    def _classify(self) -> DetectedPluck | None:
        frames = [frame for frame in self._captured_frames if frame.peaks]
        if not frames:
            return None

        candidates: dict[int, _PluckCandidate] = {}
        for frame_index, frame in enumerate(frames):
            best_by_midi = self._frame_evidence(frame, frame_index)
            for evidence in best_by_midi.values():
                candidate = candidates.setdefault(evidence.midi, _PluckCandidate(midi=evidence.midi))
                candidate.score += evidence.score
                candidate.weighted_frequency += evidence.frequency_hz * evidence.score
                candidate.weight += evidence.score
                candidate.harmonic_multiples.update(evidence.harmonic_multiples)
                candidate.frame_indexes.add(evidence.frame_index)

        if not candidates:
            return None

        candidate = max(candidates.values(), key=self._candidate_score)
        if candidate.weight <= 0:
            return None

        frequency_hz = candidate.weighted_frequency / candidate.weight
        note_name = frequency_to_note(note_to_frequency(candidate.midi))[1]
        dominant_peak = max(
            (frame.dominant_peak for frame in frames if frame.dominant_peak is not None),
            key=lambda peak: peak.relative_percent,
            default=None,
        )
        harmonic_multiples = tuple(
            multiple
            for multiple in sorted(candidate.harmonic_multiples)
            if multiple > 1
        )
        harmonic_matches = format_multiples(harmonic_multiples).split(", ") if harmonic_multiples else []
        confidence = self._confidence(candidate, len(frames), harmonic_multiples)
        reason = self._reason(frequency_hz, harmonic_matches)
        open_string_families = self._open_string_detector.analyze_frames(frames)
        return DetectedPluck(
            note_name=note_name,
            midi=candidate.midi,
            frequency_hz=frequency_hz,
            confidence=confidence,
            dominant_frequency_hz=dominant_peak.frequency_hz if dominant_peak is not None else frequency_hz,
            harmonic_matches=harmonic_matches,
            started_at=self._started_at,
            ended_at=None,
            reason=reason,
            open_string_families=open_string_families,
        )

    def _frame_evidence(self, frame: PitchFrame, frame_index: int) -> dict[int, _PluckEvidence]:
        best_by_midi: dict[int, _PluckEvidence] = {}
        for source_peak in frame.peaks:
            for divisor in range(1, 7):
                candidate_frequency = source_peak.frequency_hz / divisor
                if candidate_frequency < MIN_HZ or candidate_frequency > MAX_HZ:
                    continue
                midi, _note = frequency_to_note(candidate_frequency)
                matches = self._harmonic_matches(candidate_frequency, frame.peaks)
                if not matches:
                    continue
                harmonic_bonus = 0.8 if any(multiple > 1 for multiple, _peak in matches) else 0.0
                estimated_bonus = 0.5 if frame.likely_fundamental and frame.likely_fundamental.midi == midi else 0.0
                score = (
                    len(matches) * 2.0
                    + sum(peak.relative_percent / 100.0 for _multiple, peak in matches)
                    + harmonic_bonus
                    + estimated_bonus
                    + frame.confidence * 0.5
                    + source_peak.relative_percent / 200.0
                    - candidate_frequency * 0.0004
                )
                evidence = _PluckEvidence(
                    midi=midi,
                    frequency_hz=candidate_frequency,
                    score=max(score, 0.01),
                    harmonic_multiples=tuple(multiple for multiple, _peak in matches),
                    frame_index=frame_index,
                )
                current = best_by_midi.get(midi)
                if current is None or evidence.score > current.score:
                    best_by_midi[midi] = evidence
        return best_by_midi

    def _harmonic_matches(
        self,
        candidate_frequency: float,
        peaks: tuple[SpectrumPeak, ...],
    ) -> tuple[tuple[int, SpectrumPeak], ...]:
        matches: list[tuple[int, SpectrumPeak]] = []
        for multiple in range(1, 7):
            possible_matches = [
                peak
                for peak in peaks
                if peak.relative_percent >= 8.0
                and harmonic_error(candidate_frequency, peak.frequency_hz, multiple) <= 0.035
            ]
            if possible_matches:
                matches.append(
                    (
                        multiple,
                        min(
                            possible_matches,
                            key=lambda peak: harmonic_error(candidate_frequency, peak.frequency_hz, multiple),
                        ),
                    )
                )
        return tuple(matches)

    def _candidate_score(self, candidate: _PluckCandidate) -> float:
        harmonic_multiples = candidate.harmonic_multiples or set()
        frame_indexes = candidate.frame_indexes or set()
        harmonic_depth = len([multiple for multiple in harmonic_multiples if multiple > 1])
        has_fundamental = 1 in harmonic_multiples
        return (
            candidate.score
            + len(frame_indexes) * 2.0
            + harmonic_depth * 1.5
            + (1.0 if has_fundamental and harmonic_depth else 0.0)
        )

    def _confidence(
        self,
        candidate: _PluckCandidate,
        frame_count: int,
        harmonic_multiples: tuple[int, ...],
    ) -> float:
        persistence = len(candidate.frame_indexes or set()) / max(frame_count, 1)
        harmonic_depth = min(len(harmonic_multiples), 4) / 4.0
        score_strength = min(candidate.score / max(frame_count * 5.0, 1.0), 1.0)
        return min(1.0, 0.25 + persistence * 0.35 + harmonic_depth * 0.25 + score_strength * 0.15)

    def _reason(self, frequency_hz: float, harmonic_matches: list[str]) -> str:
        if harmonic_matches:
            return f"{frequency_hz:.1f} Hz explains harmonics at {', '.join(harmonic_matches)}"
        return f"{frequency_hz:.1f} Hz was the most persistent fundamental candidate"


def sounddevice_available() -> bool:
    """Return whether the runtime can import the PortAudio adapter.

    @author Codex - created live sandbox audio boundary.
    """

    return sd is not None


def list_input_devices() -> list[AudioDevice]:
    """Return all PortAudio devices that can capture input.

    @author Codex - created live sandbox audio boundary.
    """

    if sd is None:
        return []
    devices: list[AudioDevice] = []
    for index, device in enumerate(sd.query_devices()):
        channels = int(device["max_input_channels"])
        if channels <= 0:
            continue
        devices.append(
            AudioDevice(
                index=index,
                name=str(device["name"]),
                input_channels=channels,
                default_sample_rate=int(float(device["default_samplerate"])),
            )
        )
    return devices


def choose_sample_rate(device_index: int, requested_rate: int = DEFAULT_SAMPLE_RATE) -> int:
    """Prefer the detector's 48 kHz rate and fall back to the device default.

    @author Codex - ported old detector device negotiation into sandbox boundary.
    """

    if sd is None:
        raise RuntimeError("sounddevice is not installed")
    try:
        sd.check_input_settings(device=device_index, channels=DEFAULT_CHANNELS, samplerate=requested_rate)
        return requested_rate
    except Exception:
        device = sd.query_devices(device_index)
        return int(float(device["default_samplerate"]))


class LivePitchInput:
    """Capture live audio buffers and expose analyzed detector frames.

    The class is intentionally stateful because PortAudio streams are resources.
    The Qt view starts/stops this object, but all audio policy remains here.

    @author Codex - created live sandbox audio boundary.
    """

    def __init__(self, rms_threshold: float = 0.01):
        self._rms_threshold = rms_threshold
        self._sample_rate = DEFAULT_SAMPLE_RATE
        self._stream: Any | None = None
        self._blocks: queue.Queue[np.ndarray] = queue.Queue(maxsize=4)

    @property
    def sample_rate(self) -> int:
        """Return the active stream sample rate.

        @author Codex - created live sandbox audio boundary.
        """

        return self._sample_rate

    def start(self, device_index: int) -> None:
        """Open the selected input device and begin buffering audio blocks.

        @author Codex - created live sandbox audio boundary.
        """

        if sd is None:
            raise RuntimeError("sounddevice is not installed")
        self.stop()
        self._sample_rate = choose_sample_rate(device_index)
        block_size = int(self._sample_rate * DEFAULT_BLOCK_MS / 1000)
        self._stream = sd.InputStream(
            device=device_index,
            channels=DEFAULT_CHANNELS,
            samplerate=self._sample_rate,
            blocksize=block_size,
            dtype="float32",
            callback=self._on_audio,
        )
        self._stream.start()

    def stop(self) -> None:
        """Close the active input stream, if any.

        @author Codex - created live sandbox audio boundary.
        """

        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        while not self._blocks.empty():
            self._blocks.get_nowait()

    def latest_frame(self) -> PitchFrame | None:
        """Return the newest analyzed frame, dropping stale queued buffers.

        @author Codex - created live sandbox audio boundary.
        """

        latest: np.ndarray | None = None
        while True:
            try:
                latest = self._blocks.get_nowait()
            except queue.Empty:
                break
        if latest is None:
            return None
        return analyze_samples(latest, self._sample_rate, rms_threshold=self._rms_threshold)

    def _on_audio(self, indata: np.ndarray, _frames: int, _time_info: Any, status: Any) -> None:
        if status:
            pass
        block = np.asarray(indata, dtype=np.float32).reshape(-1).copy()
        try:
            self._blocks.put_nowait(block)
        except queue.Full:
            _oldest = self._blocks.get_nowait()
            self._blocks.put_nowait(block)


def analyze_samples(samples: np.ndarray, sample_rate: int, rms_threshold: float = 0.01) -> PitchFrame:
    """Analyze one audio buffer into peaks, fundamental estimate, and status.

    @author Codex - ported old detector analysis into sandbox boundary.
    """

    peaks, rms, frequencies, magnitudes = find_fft_peaks(samples, sample_rate)
    if rms < rms_threshold or not peaks:
        return PitchFrame(
            rms=rms,
            dominant_peak=peaks[0] if peaks else None,
            likely_fundamental=None,
            confidence=0.0,
            harmonic_lock=False,
            reason="input below RMS threshold" if rms < rms_threshold else "no FFT peaks in guitar range",
            display_stable=False,
            peaks=tuple(peaks),
            spectrum_frequencies=frequencies,
            spectrum_magnitudes=magnitudes,
        )

    estimate = estimate_fundamental_from_peaks(peaks)
    dominant = peaks[0]
    harmonic_lock = dominant.note != estimate.peak.note
    return PitchFrame(
        rms=rms,
        dominant_peak=dominant,
        likely_fundamental=estimate.peak,
        confidence=estimate.confidence,
        harmonic_lock=harmonic_lock,
        reason=estimate.reason,
        display_stable=rms >= rms_threshold and estimate.confidence >= 0.35,
        peaks=tuple(peaks),
        spectrum_frequencies=frequencies,
        spectrum_magnitudes=magnitudes,
    )


def find_fft_peaks(
    samples: np.ndarray,
    sample_rate: int,
    *,
    count: int = 10,
    min_hz: float = MIN_HZ,
    max_hz: float = MAX_HZ,
    min_separation_hz: float = 8.0,
) -> tuple[list[SpectrumPeak], float, np.ndarray, np.ndarray]:
    """Return the strongest separated FFT peaks inside the guitar range.

    @author Codex - ported old detector FFT peak extraction into sandbox boundary.
    @author Codex - preserved more peaks for multi-string open-family diagnostics.
    """

    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(mono) == 0 or sample_rate <= 0:
        return [], 0.0, np.array([], dtype=float), np.array([], dtype=float)

    rms = calculate_rms(mono)
    mono = mono - float(np.mean(mono))
    windowed = mono * np.hanning(len(mono))
    fft_size = max(32_768, 1 << (len(windowed) - 1).bit_length())
    spectrum = np.fft.rfft(windowed, n=fft_size)
    magnitudes = np.abs(spectrum)
    freqs = np.fft.rfftfreq(fft_size, d=1.0 / sample_rate)

    mask = (freqs >= min_hz) & (freqs <= max_hz)
    if not np.any(mask):
        return [], rms, np.array([], dtype=float), np.array([], dtype=float)

    visible_freqs = freqs[mask].astype(float)
    visible_magnitudes = magnitudes[mask].astype(float)
    max_visible_magnitude = float(np.max(visible_magnitudes)) if visible_magnitudes.size else 0.0
    if max_visible_magnitude > 0:
        visible_magnitudes = visible_magnitudes / max_visible_magnitude

    local_maxima = np.zeros_like(magnitudes, dtype=bool)
    local_maxima[1:-1] = (magnitudes[1:-1] >= magnitudes[:-2]) & (magnitudes[1:-1] > magnitudes[2:])
    candidate_indices = np.where(mask & local_maxima)[0]
    if len(candidate_indices) == 0:
        masked_magnitudes = np.where(mask, magnitudes, 0.0)
        candidate_indices = np.array([int(np.argmax(masked_magnitudes))])

    candidate_indices = sorted(candidate_indices, key=lambda index: magnitudes[index], reverse=True)
    selected: list[tuple[float, float]] = []
    for peak_index in candidate_indices:
        if magnitudes[peak_index] <= 0:
            continue
        refined_index = parabolic_interpolation(magnitudes, int(peak_index))
        frequency = refined_index * sample_rate / fft_size
        if frequency < min_hz or frequency > max_hz:
            continue
        if any(abs(frequency - existing_frequency) < min_separation_hz for existing_frequency, _ in selected):
            continue
        selected.append((float(frequency), float(magnitudes[peak_index])))
        if len(selected) >= count:
            break

    if not selected:
        return [], rms, visible_freqs, visible_magnitudes

    max_magnitude = max(magnitude for _frequency, magnitude in selected)
    peaks = [
        make_peak(frequency, magnitude, max_magnitude, relationship="pending")
        for frequency, magnitude in selected
    ]
    dominant = peaks[0]
    return [peak_with_relationship(peak, dominant, peaks) for peak in peaks], rms, visible_freqs, visible_magnitudes


def make_peak(frequency_hz: float, magnitude: float, max_magnitude: float, relationship: str) -> SpectrumPeak:
    """Create a chart row from raw FFT values.

    @author Codex - created live sandbox peak chart model.
    """

    midi, note = frequency_to_note(frequency_hz)
    return SpectrumPeak(
        frequency_hz=frequency_hz,
        magnitude=magnitude,
        relative_percent=100.0 * magnitude / max(max_magnitude, 1e-9),
        midi=midi,
        note=note,
        harmonic_relationship=relationship,
    )


def peak_with_relationship(peak: SpectrumPeak, dominant: SpectrumPeak, peaks: list[SpectrumPeak]) -> SpectrumPeak:
    """Label whether a peak is dominant, fundamental candidate, or harmonic.

    @author Codex - created live sandbox peak chart model.
    """

    relationship = "dominant"
    if peak is not dominant:
        ratio = dominant.frequency_hz / peak.frequency_hz if peak.frequency_hz > 0 else 0.0
        nearest = int(round(ratio))
        if 2 <= nearest <= 6 and harmonic_error(peak.frequency_hz, dominant.frequency_hz, nearest) <= 0.03:
            relationship = f"possible fundamental of {nearest}x dominant"
        else:
            relationship = "neighbor"

    for candidate in peaks:
        if candidate is peak or candidate.frequency_hz <= peak.frequency_hz:
            continue
        ratio = candidate.frequency_hz / peak.frequency_hz
        nearest = int(round(ratio))
        if 2 <= nearest <= 6 and harmonic_error(peak.frequency_hz, candidate.frequency_hz, nearest) <= 0.03:
            relationship = "fundamental" if peak is not dominant else relationship
            break

    return SpectrumPeak(
        frequency_hz=peak.frequency_hz,
        magnitude=peak.magnitude,
        relative_percent=peak.relative_percent,
        midi=peak.midi,
        note=peak.note,
        harmonic_relationship=relationship,
    )


def calculate_rms(samples: np.ndarray) -> float:
    """Return root-mean-square volume for one audio buffer.

    @author Codex - ported old detector analysis into sandbox boundary.
    """

    mono = np.asarray(samples, dtype=np.float32).reshape(-1)
    if len(mono) == 0:
        return 0.0
    return float(np.sqrt(np.mean(np.square(mono, dtype=np.float64))))


def parabolic_interpolation(magnitudes: np.ndarray, peak_index: int) -> float:
    """Return a fractional FFT-bin index using the peak and its neighbors.

    @author Codex - ported old detector FFT peak extraction into sandbox boundary.
    """

    if peak_index <= 0 or peak_index >= len(magnitudes) - 1:
        return float(peak_index)
    left = float(magnitudes[peak_index - 1])
    center = float(magnitudes[peak_index])
    right = float(magnitudes[peak_index + 1])
    denominator = left - 2.0 * center + right
    if abs(denominator) < 1e-12:
        return float(peak_index)
    offset = 0.5 * (left - right) / denominator
    return float(peak_index + np.clip(offset, -1.0, 1.0))


def frequency_to_note(frequency_hz: float) -> tuple[int, str]:
    """Convert a frequency in Hz to the nearest MIDI note and note name.

    @author Codex - ported old detector analysis into sandbox boundary.
    """

    midi = int(round(69 + 12 * math.log2(max(frequency_hz, 1e-9) / 440.0)))
    note_name = NOTE_NAMES[midi % 12]
    octave = midi // 12 - 1
    return midi, f"{note_name}{octave}"


def note_to_frequency(midi: int) -> float:
    """Return the equal-tempered frequency for a MIDI note.

    Pluck classification groups slightly different harmonic-derived
    frequencies by MIDI note. This helper gives the event readout a stable note
    name without pretending the measured pluck frequency was quantized.

    @author Codex - added pluck-level detector between FFT frames and GUI.
    """

    return 440.0 * (2.0 ** ((midi - 69) / 12))


def harmonic_error(base_hz: float, harmonic_hz: float, multiple: int) -> float:
    """Return relative error for a harmonic candidate.

    @author Codex - ported old detector harmonic analysis into sandbox boundary.
    """

    expected = base_hz * multiple
    if expected <= 0:
        return float("inf")
    return abs(harmonic_hz - expected) / expected


def harmonic_matches_for_peak(candidate: SpectrumPeak, peaks: list[SpectrumPeak]) -> list[tuple[int, SpectrumPeak]]:
    """Find higher peaks that look like harmonics of a candidate fundamental.

    @author Codex - ported old detector harmonic analysis into sandbox boundary.
    """

    matches: list[tuple[int, SpectrumPeak]] = []
    for multiple in range(2, 6):
        possible_matches = [
            peak
            for peak in peaks
            if peak is not candidate
            and peak.frequency_hz > candidate.frequency_hz
            and peak.relative_percent >= 8.0
            and harmonic_error(candidate.frequency_hz, peak.frequency_hz, multiple) <= 0.03
        ]
        if possible_matches:
            matches.append(
                (
                    multiple,
                    min(
                        possible_matches,
                        key=lambda peak: harmonic_error(candidate.frequency_hz, peak.frequency_hz, multiple),
                    ),
                )
            )
    return matches


def estimate_fundamental_from_peaks(peaks: list[SpectrumPeak]) -> FundamentalEstimate:
    """Choose a likely played pitch from visible FFT peaks.

    The sandbox preserves the old detector's guitar-specific assumption:
    a lower peak can be the intended note when it explains multiple stronger
    upper peaks as harmonics.

    @author Codex - ported old harmonic-aware detector into sandbox boundary.
    """

    if not peaks:
        raise ValueError("estimate_fundamental_from_peaks requires at least one peak")

    dominant = peaks[0]
    best_peak = dominant
    best_matches: list[tuple[int, SpectrumPeak]] = []
    best_score = 0.0

    for candidate in sorted(peaks, key=lambda peak: peak.frequency_hz):
        if candidate.relative_percent < 12.0:
            continue
        matches = harmonic_matches_for_peak(candidate, peaks)
        if len(matches) < 2:
            continue
        harmonic_strength = sum(peak.relative_percent for _multiple, peak in matches)
        score = len(matches) * 100.0 + harmonic_strength + candidate.relative_percent - candidate.frequency_hz * 0.01
        if score > best_score:
            best_peak = candidate
            best_matches = matches
            best_score = score

    if best_matches:
        multiples = tuple(multiple for multiple, _peak in best_matches)
        confidence = min(1.0, 0.45 + 0.15 * len(best_matches) + best_peak.relative_percent / 200.0)
        return FundamentalEstimate(
            peak=best_peak,
            confidence=confidence,
            harmonic_multiples=multiples,
            used_fallback=False,
            reason=f"{best_peak.frequency_hz:.1f} Hz explains harmonics at {format_multiples(multiples)}",
        )

    return FundamentalEstimate(
        peak=dominant,
        confidence=dominant.relative_percent / 100.0,
        harmonic_multiples=(),
        used_fallback=True,
        reason="no strong harmonic relationship found; using dominant FFT peak",
    )


def format_multiples(multiples: tuple[int, ...]) -> str:
    """Format harmonic numbers as compact labels.

    @author Codex - ported old detector harmonic analysis into sandbox boundary.
    """

    return ", ".join(f"{multiple}x" for multiple in multiples)
