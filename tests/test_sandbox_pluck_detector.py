import unittest

import numpy as np

from interfaces.sandbox.audio_pitch import (
    OpenStringFamilyDetector,
    PitchFrame,
    PluckDetector,
    SpectrumPeak,
    frequency_to_note,
)


def peak(frequency_hz: float, relative_percent: float = 100.0) -> SpectrumPeak:
    midi, note = frequency_to_note(frequency_hz)
    return SpectrumPeak(
        frequency_hz=frequency_hz,
        magnitude=relative_percent,
        relative_percent=relative_percent,
        midi=midi,
        note=note,
        harmonic_relationship="dominant",
    )


def frame(frequency_hz: float | None, rms: float, confidence: float = 0.85) -> PitchFrame:
    peaks = (peak(frequency_hz),) if frequency_hz is not None else ()
    return frame_with_peaks(peaks, rms, confidence)


def frame_with_peaks(
    peaks: tuple[SpectrumPeak, ...],
    rms: float,
    confidence: float = 0.85,
) -> PitchFrame:
    dominant = peaks[0] if peaks else None
    return PitchFrame(
        rms=rms,
        dominant_peak=dominant,
        likely_fundamental=dominant,
        confidence=confidence if dominant else 0.0,
        harmonic_lock=False,
        reason="synthetic frame",
        display_stable=dominant is not None,
        peaks=peaks,
        spectrum_frequencies=np.array([], dtype=float),
        spectrum_magnitudes=np.array([], dtype=float),
    )


def evidence_by_name(report):
    return {family.string_name: family for family in report.families}


OPEN_STRING_FREQUENCIES = {
    "E2": 82.41,
    "A2": 110.00,
    "D3": 146.83,
    "G3": 196.00,
    "B3": 246.94,
    "E4": 329.63,
}
SYNTHETIC_HARMONIC_STRENGTHS = {
    1: 90.0,
    2: 62.0,
    3: 48.0,
    4: 34.0,
    5: 22.0,
    6: 16.0,
}


def open_string_frame(string_names: tuple[str, ...]) -> PitchFrame:
    return open_string_frame_with_strengths(
        {
            string_name: SYNTHETIC_HARMONIC_STRENGTHS
            for string_name in string_names
        }
    )


def open_string_frame_with_strengths(strengths_by_string: dict[str, dict[int, float]]) -> PitchFrame:
    peaks_by_frequency: dict[float, float] = {}
    for string_name, strengths in strengths_by_string.items():
        base_frequency = OPEN_STRING_FREQUENCIES[string_name]
        for harmonic, strength in strengths.items():
            frequency = round(base_frequency * harmonic, 1)
            if frequency <= 1200.0:
                peaks_by_frequency[frequency] = max(peaks_by_frequency.get(frequency, 0.0), strength)
    peaks = tuple(
        sorted(
            (peak(frequency, strength) for frequency, strength in peaks_by_frequency.items()),
            key=lambda spectrum_peak: spectrum_peak.relative_percent,
            reverse=True,
        )
    )
    return frame_with_peaks(peaks, rms=0.030)


WEAK_LOW_STRING_STRENGTHS = {
    1: 5.0,
    2: 11.0,
    3: 26.0,
    4: 24.0,
    5: 14.0,
    6: 12.0,
}
STRONG_OPEN_STRING_STRENGTHS = {
    1: 84.0,
    2: 56.0,
    3: 40.0,
    4: 28.0,
    5: 18.0,
    6: 12.0,
}


class PluckDetectorTests(unittest.TestCase):
    def test_low_e_pluck_is_classified_from_harmonics_across_capture_window(self):
        detector = PluckDetector(capture_window_seconds=0.16)
        frames = [
            (0.00, frame(None, 0.001)),
            (0.05, frame(81.3, 0.030)),
            (0.10, frame(162.7, 0.028)),
            (0.15, frame(245.0, 0.024)),
            (0.22, frame(326.2, 0.020)),
        ]

        events = [detector.process_frame(pitch_frame, now) for now, pitch_frame in frames]
        pluck = next(event for event in events if event is not None)

        self.assertEqual(pluck.note_name, "E2")
        self.assertEqual(pluck.midi, 40)
        self.assertAlmostEqual(pluck.frequency_hz, 81.4, delta=1.0)
        self.assertEqual(pluck.harmonic_matches, ["2x", "3x", "4x"])
        self.assertGreaterEqual(pluck.confidence, 0.85)
        self.assertIn("explains harmonics", pluck.reason)
        self.assertIsNone(pluck.ended_at)

    def test_latched_pluck_does_not_emit_frame_level_note_changes_during_decay(self):
        detector = PluckDetector(capture_window_seconds=0.16)
        setup_frames = [
            (0.00, frame(None, 0.001)),
            (0.05, frame(81.3, 0.030)),
            (0.10, frame(162.7, 0.028)),
            (0.15, frame(245.0, 0.024)),
            (0.22, frame(326.2, 0.020)),
        ]
        pluck = None
        for now, pitch_frame in setup_frames:
            pluck = detector.process_frame(pitch_frame, now) or pluck

        decay_events = [
            detector.process_frame(frame(162.7, 0.016), 0.26),
            detector.process_frame(frame(245.0, 0.013), 0.31),
            detector.process_frame(frame(326.2, 0.010), 0.36),
        ]

        self.assertIsNotNone(pluck)
        self.assertEqual(detector.current_pluck.note_name, "E2")
        self.assertEqual(decay_events, [None, None, None])
        self.assertEqual(detector.state, PluckDetector.LATCHED)


class OpenStringFamilyDetectorTests(unittest.TestCase):
    def test_all_single_open_strings_mark_only_the_plucked_family_active(self):
        detector = OpenStringFamilyDetector()

        for string_name in OPEN_STRING_FREQUENCIES:
            with self.subTest(string_name=string_name):
                report = detector.analyze_frames([open_string_frame((string_name,))])
                families = evidence_by_name(report)

                self.assertEqual(families[string_name].status, "active")
                for other_name, family in families.items():
                    if other_name != string_name:
                        self.assertNotEqual(family.status, "active")

    def test_adjacent_open_string_pairs_keep_both_real_families_active(self):
        detector = OpenStringFamilyDetector()
        adjacent_pairs = (
            ("E2", "A2"),
            ("A2", "D3"),
            ("D3", "G3"),
            ("G3", "B3"),
            ("B3", "E4"),
        )

        for first, second in adjacent_pairs:
            with self.subTest(pair=f"{first}+{second}"):
                report = detector.analyze_frames([open_string_frame((first, second))])
                families = evidence_by_name(report)

                self.assertEqual(families[first].status, "active")
                self.assertEqual(families[second].status, "active")

    def test_late_harmonics_without_anchor_do_not_create_uncertain_family(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames([open_string_frame(("G3", "B3"))])
        families = evidence_by_name(report)

        self.assertEqual(families["G3"].status, "active")
        self.assertEqual(families["B3"].status, "active")
        self.assertNotEqual(families["D3"].status, "uncertain")
        self.assertIn("upper harmonics are diagnostic only", families["D3"].debug_text)

    def test_lower_four_string_pluck_keeps_weak_e2_a2_anchor_evidence_visible(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                open_string_frame_with_strengths(
                    {
                        "E2": WEAK_LOW_STRING_STRENGTHS,
                        "A2": WEAK_LOW_STRING_STRENGTHS,
                        "D3": STRONG_OPEN_STRING_STRENGTHS,
                        "G3": STRONG_OPEN_STRING_STRENGTHS,
                    }
                )
            ]
        )
        families = evidence_by_name(report)

        self.assertIn(families["E2"].status, {"active", "uncertain"})
        self.assertIn(families["A2"].status, {"active", "uncertain"})
        self.assertEqual(families["D3"].status, "active")
        self.assertEqual(families["G3"].status, "active")
        self.assertIn("low-string trace", families["E2"].debug_text)
        self.assertIn("1x~82Hz weak", families["E2"].debug_text)
        self.assertIn("2x~165Hz present", families["E2"].debug_text)
        self.assertIn("low-string trace", families["A2"].debug_text)
        self.assertIn("1x~110Hz weak", families["A2"].debug_text)
        self.assertIn("2x~220Hz present", families["A2"].debug_text)

    def test_all_open_string_pluck_keeps_every_family_visible_with_weak_low_anchors(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                open_string_frame_with_strengths(
                    {
                        "E2": WEAK_LOW_STRING_STRENGTHS,
                        "A2": WEAK_LOW_STRING_STRENGTHS,
                        "D3": STRONG_OPEN_STRING_STRENGTHS,
                        "G3": STRONG_OPEN_STRING_STRENGTHS,
                        "B3": STRONG_OPEN_STRING_STRENGTHS,
                        "E4": STRONG_OPEN_STRING_STRENGTHS,
                    }
                )
            ]
        )

        for family in report.families:
            with self.subTest(string_name=family.string_name):
                self.assertNotEqual(family.status, "inactive")

        families = evidence_by_name(report)
        self.assertIn(families["E2"].status, {"active", "uncertain"})
        self.assertIn(families["A2"].status, {"active", "uncertain"})
        self.assertIn("low-string trace", families["E2"].debug_text)
        self.assertIn("low-string trace", families["A2"].debug_text)

    def test_low_strings_do_not_activate_from_upper_harmonics_without_anchors(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(247.0, 48.0),
                        peak(329.0, 42.0),
                        peak(412.0, 30.0),
                        peak(494.0, 26.0),
                        peak(330.0, 44.0),
                        peak(440.0, 34.0),
                        peak(550.0, 28.0),
                        peak(660.0, 24.0),
                    ),
                    rms=0.030,
                )
            ]
        )
        families = evidence_by_name(report)

        self.assertNotEqual(families["E2"].status, "active")
        self.assertNotEqual(families["A2"].status, "active")
        self.assertIn("upper harmonics are diagnostic only", families["E2"].debug_text)
        self.assertIn("upper harmonics are diagnostic only", families["A2"].debug_text)

    def test_higher_string_fundamental_overlap_can_still_be_active_with_independent_support(self):
        detector = OpenStringFamilyDetector()
        harmonic_pairs = (
            ("E2", "B3"),
            ("E2", "E4"),
            ("A2", "E4"),
        )

        for lower_string, higher_string in harmonic_pairs:
            with self.subTest(pair=f"{lower_string}+{higher_string}"):
                report = detector.analyze_frames([open_string_frame((lower_string, higher_string))])
                families = evidence_by_name(report)

                self.assertEqual(families[lower_string].status, "active")
                self.assertEqual(families[higher_string].status, "active")
                self.assertIn("co-present string", families[higher_string].debug_text)

    def test_overlapped_anchor_with_only_late_support_stays_overlap_not_active(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames([open_string_frame(("E2", "E4"))])
        families = evidence_by_name(report)

        self.assertEqual(families["E2"].status, "active")
        self.assertEqual(families["E4"].status, "active")
        self.assertEqual(families["B3"].status, "harmonic overlap")
        self.assertIn("upper harmonics are diagnostic only", families["B3"].debug_text)

    def test_single_low_e_marks_e2_active_and_high_strings_as_overlap(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(245.5, 100.0),
                        peak(81.3, 56.0),
                        peak(162.7, 38.0),
                        peak(489.8, 23.0),
                        peak(326.2, 23.0),
                    ),
                    rms=0.030,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["E2"].status, "active")
        self.assertGreaterEqual(families["E2"].score_percent, 55.0)
        self.assertEqual(families["A2"].status, "inactive")
        self.assertEqual(families["D3"].status, "inactive")
        self.assertIn(families["B3"].status, {"harmonic overlap", "inactive"})
        self.assertIn(families["E4"].status, {"harmonic overlap", "inactive"})
        self.assertNotEqual(families["E4"].status, "active")

    def test_single_a_marks_a2_active_and_other_strings_low_or_overlap(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(330.0, 100.0),
                        peak(110.0, 75.0),
                        peak(220.0, 42.0),
                        peak(440.0, 36.0),
                    ),
                    rms=0.030,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["A2"].status, "active")
        self.assertGreaterEqual(families["A2"].score_percent, 55.0)
        self.assertNotEqual(families["E2"].status, "active")
        self.assertNotEqual(families["D3"].status, "active")
        self.assertNotEqual(families["E4"].status, "active")

    def test_single_high_e_marks_e4_active_without_promoting_a2_subharmonic(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(330.0, 100.0),
                        peak(660.0, 60.0),
                        peak(990.0, 35.0),
                    ),
                    rms=0.030,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["E4"].status, "active")
        self.assertEqual(report.ranked[0].string_name, "E4")
        self.assertNotEqual(families["A2"].status, "active")
        self.assertIn(families["A2"].status, {"harmonic overlap", "inactive"})

    def test_low_e_and_a_pluck_reports_both_families(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(245.5, 100.0),
                        peak(81.3, 52.0),
                        peak(162.7, 34.0),
                        peak(110.0, 46.0),
                        peak(220.0, 28.0),
                        peak(330.0, 40.0),
                    ),
                    rms=0.034,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["E2"].status, "active")
        self.assertIn(families["A2"].status, {"active", "uncertain"})
        self.assertGreaterEqual(families["A2"].score_percent, 20.0)

    def test_upper_open_strings_are_not_active_from_low_e_harmonics_only(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(82.4, 65.0),
                        peak(164.8, 45.0),
                        peak(247.2, 90.0),
                        peak(329.6, 55.0),
                        peak(494.4, 35.0),
                    ),
                    rms=0.032,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["E2"].status, "active")
        self.assertNotEqual(families["B3"].status, "active")
        self.assertNotEqual(families["E4"].status, "active")
        self.assertIn("overlap", families["B3"].debug_text)
        self.assertIn("overlap", families["E4"].debug_text)

    def test_low_e_harmonic_near_high_e_does_not_activate_e4(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(82.0, 72.0),
                        peak(164.0, 52.0),
                        peak(245.0, 44.0),
                        peak(328.0, 42.0),
                    ),
                    rms=0.031,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["E2"].status, "active")
        self.assertNotEqual(families["E4"].status, "active")
        self.assertIn(families["E4"].status, {"harmonic overlap", "inactive"})

    def test_a2_harmonic_near_high_e_does_not_activate_e4(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames(
            [
                frame_with_peaks(
                    (
                        peak(110.0, 82.0),
                        peak(220.0, 56.0),
                        peak(330.0, 68.0),
                        peak(440.0, 44.0),
                    ),
                    rms=0.031,
                )
            ]
        )

        families = evidence_by_name(report)

        self.assertEqual(families["A2"].status, "active")
        self.assertNotEqual(families["E4"].status, "active")
        self.assertIn(families["E4"].status, {"harmonic overlap", "inactive"})

    def test_empty_frames_return_inactive_open_string_report(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames([frame(None, rms=0.001)])

        self.assertEqual(len(report.families), 6)
        self.assertTrue(all(family.status == "inactive" for family in report.families))
        self.assertTrue(all(family.score_percent == 0.0 for family in report.families))


if __name__ == "__main__":
    unittest.main()
