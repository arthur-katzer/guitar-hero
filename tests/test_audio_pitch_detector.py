import unittest

import numpy as np

import audio_pitch_detector as detector


SAMPLE_RATE = 48000


def sine(frequency_hz, duration=1.0, amplitude=0.4):
    t = np.linspace(0.0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return amplitude * np.sin(2.0 * np.pi * frequency_hz * t)


def peak(frequency_hz, relative_percent):
    midi, note = detector.frequency_to_note(frequency_hz)
    return detector.FftPeak(
        frequency_hz=frequency_hz,
        magnitude=relative_percent,
        relative_percent=relative_percent,
        midi=midi,
        note=note,
    )


def observed_low_e_peaks():
    return [
        peak(245.5, 100.0),
        peak(81.3, 56.0),
        peak(162.7, 38.0),
        peak(489.8, 23.0),
        peak(326.2, 23.0),
    ]


class FundamentalEstimationTests(unittest.TestCase):
    def test_dominant_mode_keeps_naive_low_e_harmonic_result(self):
        estimate = detector.estimate_pitch_from_peaks(
            observed_low_e_peaks(),
            detector.PITCH_MODE_DOMINANT,
        )

        self.assertAlmostEqual(estimate.peak.frequency_hz, 245.5, delta=1.0)
        self.assertEqual(estimate.peak.note, "B3")
        self.assertEqual(estimate.peak.midi, 59)
        self.assertEqual(estimate.reason, "strongest FFT peak only")

    def test_fundamental_mode_fixes_observed_low_e_peaks(self):
        peaks = observed_low_e_peaks()

        estimate = detector.estimate_pitch_from_peaks(peaks, detector.PITCH_MODE_FUNDAMENTAL)

        self.assertAlmostEqual(estimate.peak.frequency_hz, 81.3, delta=1.0)
        self.assertEqual(estimate.peak.note, "E2")
        self.assertEqual(estimate.peak.midi, 40)
        self.assertEqual(estimate.harmonic_multiples, (2, 3, 4))
        self.assertFalse(estimate.used_fallback)

    def test_synthetic_low_e_with_strong_third_harmonic(self):
        samples = (
            sine(82.41, amplitude=0.05)
            + sine(164.82, amplitude=0.07)
            + sine(247.23, amplitude=0.12)
            + sine(329.64, amplitude=0.04)
        ).astype(np.float32)

        peaks, rms = detector.find_fft_peaks(
            samples,
            SAMPLE_RATE,
            count=8,
            min_hz=detector.DIAGNOSTIC_MIN_HZ,
            max_hz=detector.MAX_GUITAR_HZ,
        )
        estimate = detector.estimate_fundamental_from_peaks(peaks)

        self.assertGreater(rms, 0.001)
        self.assertAlmostEqual(peaks[0].frequency_hz, 247.23, delta=2.0)
        self.assertEqual(peaks[0].note, "B3")
        self.assertAlmostEqual(estimate.peak.frequency_hz, 82.41, delta=2.0)
        self.assertEqual(estimate.peak.note, "E2")
        self.assertEqual(estimate.peak.midi, 40)

    def test_clean_sine_returns_same_pitch_in_both_modes(self):
        samples = sine(110.0, amplitude=0.3).astype(np.float32)

        peaks, rms = detector.find_fft_peaks(
            samples,
            SAMPLE_RATE,
            min_hz=detector.DIAGNOSTIC_MIN_HZ,
            max_hz=detector.MAX_GUITAR_HZ,
        )
        dominant = detector.estimate_pitch_from_peaks(peaks, detector.PITCH_MODE_DOMINANT)
        fundamental = detector.estimate_pitch_from_peaks(peaks, detector.PITCH_MODE_FUNDAMENTAL)

        self.assertGreater(rms, 0.001)
        self.assertAlmostEqual(dominant.peak.frequency_hz, 110.0, delta=1.0)
        self.assertAlmostEqual(fundamental.peak.frequency_hz, 110.0, delta=1.0)
        self.assertEqual(dominant.peak.midi, fundamental.peak.midi)


if __name__ == "__main__":
    unittest.main()
