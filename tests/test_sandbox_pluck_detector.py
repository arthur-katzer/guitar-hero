import unittest

import numpy as np

from interfaces.sandbox.audio_pitch import PitchFrame, PluckDetector, SpectrumPeak, frequency_to_note


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


if __name__ == "__main__":
    unittest.main()
