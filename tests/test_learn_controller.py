import unittest

from interfaces.learn.controller import LearnController, match_target
from interfaces.learn.midi_targets import MidiNoteEvent, group_note_events, section_from_targets
from interfaces.learn.model import Feedback
from interfaces.learn.transposition import apply_transpose


class LearnControllerTests(unittest.TestCase):
    def test_single_note_target_requires_exact_match(self):
        target = self._section([40]).targets[0]

        miss = match_target(target, {41})
        hit = match_target(target, {40}, confidence=0.95)

        self.assertFalse(miss.passed)
        self.assertEqual(miss.feedback, Feedback.WAITING)
        self.assertTrue(hit.passed)
        self.assertEqual(hit.feedback, Feedback.PERFECT)

    def test_multi_note_target_accepts_required_partial_ratio(self):
        target = self._section([40, 45, 47, 52]).targets[0]

        partial = match_target(target, {40, 47, 52}, confidence=0.70)
        fail = match_target(target, {40})

        self.assertTrue(partial.passed)
        self.assertEqual(partial.feedback, Feedback.GOOD)
        self.assertEqual(partial.missing_notes, (45,))
        self.assertFalse(fail.passed)

    def test_matching_uses_transposed_notes(self):
        raw_section = self._section([38])
        target = apply_transpose(raw_section.targets, 2)[0]

        miss = match_target(target, {38})
        hit = match_target(target, {40}, confidence=0.95)

        self.assertEqual(target.original_midi_notes, [38])
        self.assertFalse(miss.passed)
        self.assertTrue(hit.passed)
        self.assertEqual(hit.feedback, Feedback.PERFECT)

    def test_wait_mode_advances_only_after_current_target_match(self):
        controller = LearnController()
        controller.set_section(self._sequence_section())
        controller.start(0.0)

        waiting = controller.process_detected_note(41, confidence=1.0)
        passed = controller.process_detected_note(40, confidence=1.0)

        self.assertEqual(waiting.current_index, 0)
        self.assertEqual(waiting.feedback, Feedback.WAITING)
        self.assertEqual(passed.current_index, 1)
        self.assertEqual(passed.passed_count, 1)
        self.assertEqual(passed.feedback, Feedback.PERFECT)

    def test_update_does_not_advance_wait_only_practice_on_wall_clock(self):
        controller = LearnController()
        controller.set_section(self._sequence_section())
        before = controller.snapshot()

        after = controller.update(10.0)

        self.assertEqual(after.current_index, before.current_index)
        self.assertEqual(after.playhead_time, before.playhead_time)
        self.assertEqual(after.missed_count, 0)

    def test_region_selection_clamps_and_filters_targets(self):
        controller = LearnController()
        controller.set_section(self._sequence_section())

        state = controller.set_region(-1.0, 0.80)

        self.assertAlmostEqual(controller.region.start_time, 0.0)
        self.assertAlmostEqual(controller.region.end_time, 0.80)
        self.assertEqual(state.selected_count, 2)

    def _section(self, midi_notes):
        events = [
            MidiNoteEvent(
                start_time=0.0 + (index * 0.010),
                end_time=0.30,
                midi_note=midi_note,
                velocity=1.0,
                channel=0,
            )
            for index, midi_note in enumerate(midi_notes)
        ]
        return section_from_targets(group_note_events(events, grouping_tolerance_seconds=0.050))

    def _sequence_section(self):
        events = [
            MidiNoteEvent(0.0, 0.20, 40, 1.0, 0),
            MidiNoteEvent(0.75, 0.95, 45, 1.0, 0),
            MidiNoteEvent(1.50, 1.70, 50, 1.0, 0),
        ]
        return section_from_targets(group_note_events(events, grouping_tolerance_seconds=0.050))


if __name__ == "__main__":
    unittest.main()
