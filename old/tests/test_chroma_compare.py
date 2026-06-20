import unittest

import numpy as np

from audio.chroma_compare import (
    ChromaSequence,
    MidiNote,
    align_chroma_dtw,
    compare_chroma,
    midi_notes_to_chroma,
)
from audio_detection.cli.live_chroma_test import capture_and_detect


SAMPLE_RATE = 48000


def sequence(vectors):
    chroma = np.asarray(vectors, dtype=np.float64)
    times = np.arange(len(chroma), dtype=np.float64)
    return ChromaSequence(
        chroma=chroma,
        times=times,
        energy=np.linalg.norm(chroma, axis=1),
        frame_rate=1.0,
        label="test",
    )


class ChromaCompareTests(unittest.TestCase):
    def test_midi_notes_to_chroma_builds_pitch_class_frames(self):
        notes = [
            MidiNote(start=0.0, end=1.0, note=60, velocity=1.0),
            MidiNote(start=0.0, end=1.0, note=64, velocity=1.0),
            MidiNote(start=0.0, end=1.0, note=67, velocity=1.0),
        ]
        result = midi_notes_to_chroma(notes, times=np.asarray([0.0, 0.5, 1.5]))

        self.assertGreater(result.chroma[0, 0], 0.0)
        self.assertGreater(result.chroma[0, 4], 0.0)
        self.assertGreater(result.chroma[0, 7], 0.0)
        self.assertEqual(float(np.sum(result.chroma[2])), 0.0)

    def test_fixed_comparison_scores_identical_sequences_high(self):
        c_major = np.zeros((3, 12), dtype=np.float64)
        c_major[:, [0, 4, 7]] = 1.0
        audio = sequence(c_major)
        midi = sequence(c_major)

        result = compare_chroma(audio, midi, alignment="fixed")

        self.assertAlmostEqual(result.mean_similarity, 1.0, places=6)
        self.assertTrue(all(row.status == "likely_match" for row in result.rows))

    def test_dtw_alignment_handles_extra_reference_frame(self):
        eye = np.eye(12, dtype=np.float64)
        audio = sequence([eye[0], eye[4], eye[7]])
        midi = sequence([eye[0], eye[0], eye[4], eye[7]])

        path = align_chroma_dtw(audio.chroma, midi.chroma)
        result = compare_chroma(audio, midi, alignment="dtw")

        self.assertTrue(path)
        self.assertGreater(result.mean_similarity, 0.9)

    def test_live_chroma_free_detection_returns_chord_and_heard_chroma(self):
        duration = 0.75
        t = np.arange(int(SAMPLE_RATE * duration), dtype=np.float64) / SAMPLE_RATE
        c_major = (
            0.4 * np.sin(2 * np.pi * 261.63 * t)
            + 0.4 * np.sin(2 * np.pi * 329.63 * t)
            + 0.4 * np.sin(2 * np.pi * 392.00 * t)
        ).astype(np.float32)
        sounddevice = FakeSoundDevice(c_major)

        result = capture_and_detect(
            sounddevice,
            sample_rate=SAMPLE_RATE,
            seconds=duration,
            hop_length=1024,
            device=None,
            chroma_method="stft",
            silence_threshold=0.001,
        )

        self.assertIn("chord", result)
        self.assertIn("heard", result)
        self.assertEqual(result["heard"].shape, (12,))
        self.assertNotEqual(result["chord"].chord_name, "Silence")


class FakeSoundDevice:
    def __init__(self, samples):
        self.samples = np.asarray(samples, dtype=np.float32)

    def rec(self, frames, *, samplerate, channels, dtype, device):
        del samplerate, device
        samples = self.samples[:frames]
        if len(samples) < frames:
            samples = np.pad(samples, (0, frames - len(samples)))
        return samples.reshape(-1, 1).astype(dtype)

    def wait(self):
        return None


if __name__ == "__main__":
    unittest.main()
