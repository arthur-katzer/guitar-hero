import tempfile
import unittest
from pathlib import Path

import mido

from interfaces.learn.midi_targets import (
    MidiNoteEvent,
    discover_midi_songs,
    group_note_events,
    load_midi_song,
    midi_note_name,
)
from interfaces.learn.transposition import (
    apply_transpose,
    auto_suggest_transpose,
    transpose_midi_note,
    validate_guitar_range,
)


class LearnMidiTargetTests(unittest.TestCase):
    def test_groups_notes_that_start_inside_tolerance_into_one_target(self):
        events = [
            MidiNoteEvent(1.000, 1.300, 40, 1.0, 0),
            MidiNoteEvent(1.012, 1.250, 47, 1.0, 0),
            MidiNoteEvent(1.020, 1.260, 52, 1.0, 0),
        ]

        targets = group_note_events(events, grouping_tolerance_seconds=0.050)

        self.assertEqual(len(targets), 1)
        self.assertEqual(targets[0].midi_notes, [40, 47, 52])
        self.assertEqual(targets[0].label, "E2 + B2 + E3")
        self.assertEqual(targets[0].required_match_ratio, 0.70)

    def test_grouping_tolerance_starts_a_new_target_after_anchor_window(self):
        events = [
            MidiNoteEvent(1.000, 1.100, 40, 1.0, 0),
            MidiNoteEvent(1.049, 1.149, 45, 1.0, 0),
            MidiNoteEvent(1.061, 1.161, 50, 1.0, 0),
        ]

        targets = group_note_events(events, grouping_tolerance_seconds=0.050)

        self.assertEqual([target.midi_notes for target in targets], [[40, 45], [50]])

    def test_transposes_midi_notes_and_updates_target_labels(self):
        targets = group_note_events([MidiNoteEvent(0.0, 0.3, 38, 1.0, 0)])

        transposed = apply_transpose(targets, 2)

        self.assertEqual(transpose_midi_note(38, 2), 40)
        self.assertEqual(transposed[0].original_midi_notes, [38])
        self.assertEqual(transposed[0].midi_notes, [40])
        self.assertEqual(transposed[0].transposed_midi_notes, [40])
        self.assertEqual(transposed[0].note_names, ["E2"])
        self.assertEqual(transposed[0].label, "E2")

    def test_transpose_does_not_mutate_original_midi_notes(self):
        targets = group_note_events([MidiNoteEvent(0.0, 0.3, 38, 1.0, 0)])

        transposed = apply_transpose(targets, 2)

        self.assertEqual(targets[0].original_midi_notes, [38])
        self.assertEqual(targets[0].midi_notes, [38])
        self.assertEqual(targets[0].label, "D2")
        self.assertEqual(transposed[0].midi_notes, [40])

    def test_guitar_range_validation_uses_transposed_notes(self):
        targets = group_note_events([MidiNoteEvent(0.0, 0.3, 38, 1.0, 0)])

        raw_validation = validate_guitar_range(apply_transpose(targets, 0))
        fixed_validation = validate_guitar_range(apply_transpose(targets, 2))

        self.assertTrue(raw_validation.has_below_range_notes)
        self.assertEqual(raw_validation.lowest_note, 38)
        self.assertFalse(fixed_validation.has_below_range_notes)
        self.assertEqual(fixed_validation.lowest_note, 40)
        self.assertEqual(auto_suggest_transpose(targets), 2)

    def test_load_midi_song_excludes_percussion_and_requires_explicit_track_choice(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            midi_path = Path(tmp_dir) / "multi_track.mid"
            self._write_multi_track_midi(midi_path)

            song = load_midi_song(midi_path)

        self.assertTrue(song.requires_track_choice)
        self.assertEqual([track.name for track in song.tracks], ["GTR", "MELODY"])
        self.assertEqual([track.section.targets[0].midi_notes for track in song.tracks], [[40], [45]])
        self.assertEqual([track.note_count for track in song.tracks], [1, 1])
        self.assertEqual(song.tracks[0].notes[0].midi_note, 40)
        self.assertAlmostEqual(song.tracks[0].notes[0].start_time, 0.0)
        self.assertAlmostEqual(song.tracks[0].notes[0].end_time, 0.5)
        self.assertEqual(song.tracks[0].color, "#21d4fd")
        self.assertEqual(song.tracks[0].instrument_labels, ("Program 25",))
        self.assertEqual(song.measure_marks[0].label, "1")
        self.assertAlmostEqual(song.measure_marks[0].start_time, 0.0)
        self.assertEqual(midi_note_name(64), "E4")

    def test_discovers_song_library_midis_before_legacy_visualizer_midis(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            project_root = Path(tmp_dir)
            song_dir = project_root / "assets" / "songs" / "midi"
            legacy_dir = project_root / "assets" / "visualizer"
            song_dir.mkdir(parents=True)
            legacy_dir.mkdir(parents=True)
            library_midi = song_dir / "library.mid"
            legacy_midi = legacy_dir / "legacy.mid"
            library_midi.touch()
            legacy_midi.touch()

            songs = discover_midi_songs(project_root)

        self.assertEqual(songs, [library_midi, legacy_midi])

    def _write_multi_track_midi(self, midi_path: Path) -> None:
        mid = mido.MidiFile(type=1, ticks_per_beat=480)

        conductor = mido.MidiTrack()
        conductor.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
        conductor.append(mido.MetaMessage("time_signature", numerator=4, denominator=4, time=0))
        mid.tracks.append(conductor)

        gtr = mido.MidiTrack()
        gtr.append(mido.MetaMessage("track_name", name="GTR", time=0))
        gtr.append(mido.Message("program_change", program=24, channel=0, time=0))
        gtr.append(mido.Message("note_on", note=40, velocity=80, channel=0, time=0))
        gtr.append(mido.Message("note_off", note=40, velocity=0, channel=0, time=480))
        mid.tracks.append(gtr)

        melody = mido.MidiTrack()
        melody.append(mido.MetaMessage("track_name", name="MELODY", time=0))
        melody.append(mido.Message("program_change", program=0, channel=1, time=0))
        melody.append(mido.Message("note_on", note=45, velocity=80, channel=1, time=0))
        melody.append(mido.Message("note_off", note=45, velocity=0, channel=1, time=480))
        mid.tracks.append(melody)

        drums = mido.MidiTrack()
        drums.append(mido.MetaMessage("track_name", name="DRUMS", time=0))
        drums.append(mido.Message("note_on", note=35, velocity=80, channel=9, time=0))
        drums.append(mido.Message("note_off", note=35, velocity=0, channel=9, time=480))
        mid.tracks.append(drums)

        mid.save(midi_path)


if __name__ == "__main__":
    unittest.main()
