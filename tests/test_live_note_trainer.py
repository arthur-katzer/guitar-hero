import random
import unittest

from audio.dsp import midi_to_note_name
from live_note_trainer import ShuffledNoteChooser, note_name_to_midi, parse_note_pool


class LiveNoteTrainerTests(unittest.TestCase):
    def test_note_name_to_midi_parses_common_notes(self):
        self.assertEqual(note_name_to_midi("A4"), 69)
        self.assertEqual(note_name_to_midi("C4"), 60)
        self.assertEqual(note_name_to_midi("C#4"), 61)
        self.assertEqual(note_name_to_midi("Db4"), 61)
        self.assertEqual(note_name_to_midi("Bb3"), 58)

    def test_parse_note_pool_accepts_commas_and_spaces(self):
        notes = parse_note_pool("C4, D4 E4")
        self.assertEqual([midi_to_note_name(note) for note in notes], ["C4", "D4", "E4"])

    def test_shuffled_note_chooser_avoids_immediate_repeat_between_rounds(self):
        chooser = ShuffledNoteChooser([60, 62, 64], random.Random(3))
        previous = None
        chosen = []

        for _ in range(12):
            note = chooser.next(previous)
            if previous is not None:
                self.assertNotEqual(note, previous)
            chosen.append(note)
            previous = note

        self.assertEqual(set(chosen), {60, 62, 64})


if __name__ == "__main__":
    unittest.main()
