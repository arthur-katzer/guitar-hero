import unittest

import numpy as np

from audio.chords import detect_chord
from audio.dsp import analyze_pitch, analyze_windows, midi_to_frequency


SAMPLE_RATE = 44100


def sine(midi_note, duration=0.25, amplitude=0.4):
    frequency = midi_to_frequency(midi_note)
    t = np.linspace(0, duration, int(SAMPLE_RATE * duration), endpoint=False)
    return amplitude * np.sin(2 * np.pi * frequency * t)


class PitchDetectionTests(unittest.TestCase):
    def assert_detects_midi(self, midi_note):
        result = analyze_pitch(sine(midi_note), SAMPLE_RATE, noise_threshold=0.001)
        self.assertEqual(result.midi, midi_note)
        self.assertNotEqual(result.note_name, "Silence")
        self.assertGreater(result.confidence, 0.5)

    def test_detects_a4(self):
        self.assert_detects_midi(69)

    def test_detects_c4(self):
        self.assert_detects_midi(60)

    def test_detects_e2(self):
        self.assert_detects_midi(40)

    def test_silence_is_gated(self):
        result = analyze_pitch(np.zeros(4096), SAMPLE_RATE, noise_threshold=0.001)
        self.assertEqual(result.note_name, "Silence")
        self.assertIsNone(result.midi)

    def test_noisy_note_still_detects(self):
        rng = np.random.default_rng(123)
        samples = sine(69) + rng.normal(0.0, 0.01, int(SAMPLE_RATE * 0.25))
        result = analyze_pitch(samples, SAMPLE_RATE, noise_threshold=0.001)
        self.assertEqual(result.midi, 69)

    def test_window_timestamps_are_reported(self):
        samples = sine(69, duration=0.3)
        results = analyze_windows(samples, SAMPLE_RATE, window_ms=100, hop_ms=100)
        self.assertGreaterEqual(len(results), 3)
        self.assertAlmostEqual(results[1].start_time, 0.1, places=3)
        self.assertAlmostEqual(results[1].end_time, 0.2, places=3)


if __name__ == "__main__":
    unittest.main()


class ChordDetectionTests(unittest.TestCase):
    def test_detects_synthetic_c_major(self):
        t = np.linspace(0, 1.0, SAMPLE_RATE, endpoint=False)
        samples = (
            0.25 * np.sin(2 * np.pi * midi_to_frequency(60) * t)
            + 0.25 * np.sin(2 * np.pi * midi_to_frequency(64) * t)
            + 0.25 * np.sin(2 * np.pi * midi_to_frequency(67) * t)
        )
        result = detect_chord(samples, SAMPLE_RATE, noise_threshold=0.001)
        self.assertEqual(result.chord_name, "C maj")
        self.assertGreater(result.confidence, 0.5)


