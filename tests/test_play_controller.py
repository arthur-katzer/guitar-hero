import unittest

from interfaces.play.controller import PlayController, match_target
from interfaces.play.model import Feedback, PlaySection, PlayTarget


class PlayControllerTests(unittest.TestCase):
    def test_multi_note_target_requires_all_expected_notes(self):
        target = PlayTarget(
            start_time=0.0,
            end_time=1.0,
            original_midi_notes=[40, 44, 47],
            transposed_midi_notes=[40, 44, 47],
            note_names=["E2", "G#2", "B2"],
            label="E2 + G#2 + B2",
        )

        partial = match_target(target, {40, 44}, confidence=0.95)
        complete = match_target(target, {40, 44, 47}, confidence=0.95)

        self.assertFalse(partial.passed)
        self.assertEqual(partial.feedback, Feedback.IDLE)
        self.assertTrue(complete.passed)

    def test_confident_pluck_during_expected_silence_is_miss_without_consuming_target(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())
        controller.start(10.0)

        early = controller.process_detected_note(40, confidence=0.95, now=14.0)
        hit = controller.process_detected_note(40, confidence=0.95, now=15.0)

        self.assertEqual(early.feedback, Feedback.MISS)
        self.assertEqual(early.missed_count, 1)
        self.assertEqual(early.current_index, 0)
        self.assertEqual(hit.feedback, Feedback.PERFECT)
        self.assertEqual(hit.passed_count, 1)
        self.assertEqual(hit.missed_count, 1)

    def test_silence_during_active_sustained_target_stays_neutral_until_note_ends(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())
        controller.start(10.0)

        active_silence = controller.update(16.0)
        missed_after_end = controller.update(18.01)

        self.assertEqual(active_silence.feedback, Feedback.IDLE)
        self.assertEqual(active_silence.missed_count, 0)
        self.assertEqual(missed_after_end.feedback, Feedback.MISS)
        self.assertEqual(missed_after_end.missed_count, 1)

    def test_expected_note_can_be_hit_at_sustained_target_end(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())
        controller.start(10.0)

        hit = controller.process_detected_note(40, confidence=0.95, now=18.0)

        self.assertEqual(hit.feedback, Feedback.PERFECT)
        self.assertEqual(hit.passed_count, 1)
        self.assertEqual(hit.missed_count, 0)

    def test_low_confidence_pluck_during_silence_is_ignored(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())
        controller.start(10.0)

        ignored = controller.process_detected_note(40, confidence=0.30, now=14.0)

        self.assertEqual(ignored.feedback, Feedback.IDLE)
        self.assertEqual(ignored.missed_count, 0)

    def test_seek_inside_sustained_target_keeps_target_hittable(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())

        seeked = controller.seek(3.0)
        controller.start(10.0)
        hit = controller.process_detected_note(40, confidence=0.95, now=14.0)

        self.assertEqual(seeked.playhead_time, 3.0)
        self.assertEqual(seeked.selected_count, 1)
        self.assertEqual(hit.feedback, Feedback.PERFECT)
        self.assertEqual(hit.passed_count, 1)

    def test_seek_past_target_does_not_mark_previous_target_as_miss(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())

        seeked = controller.seek(5.5)

        self.assertEqual(seeked.playhead_time, 5.5)
        self.assertEqual(seeked.selected_count, 0)
        self.assertEqual(seeked.missed_count, 0)
        self.assertEqual(seeked.feedback, Feedback.IDLE)

    def test_speed_multiplier_advances_song_clock_faster_than_wall_clock(self):
        controller = PlayController()
        controller.set_section(self._sustained_section())
        controller.set_speed_multiplier(2.0)
        controller.start(10.0)

        state = controller.update(14.0)

        self.assertAlmostEqual(state.playhead_time, 2.0)
        self.assertEqual(state.speed_multiplier, 2.0)
        self.assertTrue(state.is_running)

    def _sustained_section(self):
        target = PlayTarget(
            start_time=2.0,
            end_time=5.0,
            original_midi_notes=[40],
            transposed_midi_notes=[40],
            note_names=["E2"],
            label="E2",
        )
        return PlaySection(start_time=0.0, end_time=6.0, targets=[target])


if __name__ == "__main__":
    unittest.main()
