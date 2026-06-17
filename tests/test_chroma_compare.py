import unittest

import numpy as np

from audio.chroma_compare import (
    ChromaSequence,
    MidiNote,
    align_chroma_dtw,
    compare_chroma,
    midi_notes_to_chroma,
)


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


if __name__ == "__main__":
    unittest.main()
