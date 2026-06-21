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

    def test_empty_frames_return_inactive_open_string_report(self):
        detector = OpenStringFamilyDetector()
        report = detector.analyze_frames([frame(None, rms=0.001)])

        self.assertEqual(len(report.families), 6)
        self.assertTrue(all(family.status == "inactive" for family in report.families))
        self.assertTrue(all(family.score_percent == 0.0 for family in report.families))


if __name__ == "__main__":
    unittest.main()
