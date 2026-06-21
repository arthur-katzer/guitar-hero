import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from interfaces.audio.pitch import AudioDevice
from interfaces.gui.main_window import MainWindow
from interfaces.learn.midi_targets import MidiNoteEvent, group_note_events, section_from_targets
from interfaces.learn.model import LearnSong, MidiNoteSpan, MidiTrackOption
from interfaces.learn.view import LearnView, PianoRollTimeline


class LearnGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_main_menu_opens_learn_without_breaking_sandbox_navigation(self):
        with patch("interfaces.learn.view.list_input_devices", return_value=[]), patch(
            "interfaces.sandbox.view.list_input_devices",
            return_value=[],
        ):
            window = MainWindow()

            window._open_option("Learn")
            self.assertIs(window.screens.currentWidget(), window.learn)

            window._show_menu()
            self.assertIs(window.screens.currentWidget(), window.background)

            window._open_option("Sandbox")
            self.assertIs(window.screens.currentWidget(), window.sandbox)

            window.close()

    def test_learn_view_uses_piano_roll_and_track_panel_controls(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        self.assertIsInstance(view.timeline, PianoRollTimeline)
        self.assertFalse(hasattr(view, "track_combo"))
        self.assertEqual(set(view._track_rows), {1, 2})
        self.assertEqual(view._controller.snapshot().selected_count, 0)

        view._select_target_track(1)

        self.assertEqual(view._controller.snapshot().selected_count, 1)
        self.assertEqual(view._controller.snapshot().current_target.midi_notes, [40])
        self.assertEqual(view.current_target_label.text(), "E2 (82.4 Hz)")
        self.assertIn("[ ] E2 (82.4 Hz)", view.expected_label.text())
        view.close()

    def test_transpose_control_updates_labels_matching_and_range_warning(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._detuned_song(),
        ):
            view = LearnView()

        self.assertEqual(view.transpose_spin.minimum(), -12)
        self.assertEqual(view.transpose_spin.maximum(), 12)
        self.assertEqual(view._controller.snapshot().current_target.midi_notes, [38])
        self.assertIn("Warning: chart contains notes below standard guitar range.", view.range_warning_label.text())

        view.transpose_spin.setValue(2)

        state = view._controller.snapshot()
        self.assertEqual(state.current_target.original_midi_notes, [38])
        self.assertEqual(state.current_target.midi_notes, [40])
        self.assertEqual(view.current_target_label.text(), "E2 (82.4 Hz)")
        self.assertIn("[ ] E2 (82.4 Hz)", view.expected_label.text())
        self.assertIn("D2 -> E2", view.transpose_preview_label.text())
        self.assertIn("Guitar range: OK.", view.range_warning_label.text())
        self.assertEqual(view._target_track.section.targets[0].midi_notes, [38])
        self.assertEqual(view.timeline._transpose_semitones, 2)
        view.close()

    def test_visible_and_audible_track_controls_are_independent(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        view._set_track_visible(2, False)

        self.assertNotIn(2, view.timeline._visible_track_indexes)
        self.assertIn(2, view._audible_track_indexes())
        self.assertEqual(view._controller.snapshot().current_target.midi_notes, [40])

        view._set_track_audible(1, False)
        self.assertIn(1, view.timeline._visible_track_indexes)
        self.assertNotIn(1, view._audible_track_indexes())
        view.close()

    def test_solo_limits_audible_tracks_without_changing_visibility(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._set_track_solo(2, True)

        self.assertEqual(view._audible_track_indexes(), frozenset({2}))
        self.assertEqual(view.timeline._visible_track_indexes, frozenset({1, 2}))
        view.close()

    def test_update_frame_shows_live_note_without_waiting_for_pluck(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._input = FakeInput(frame=live_frame(midi=40))
        view._pluck_detector = FakePluckDetector(pluck=None)

        view._update_frame()

        self.assertEqual(view.status_label.text(), "Listening.")
        self.assertIn("E2", view.detected_label.text())
        view.close()

    def test_update_frame_shows_detected_note_while_paused_without_advancing_targets(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        before = view._controller.snapshot()
        view._input = FakeInput(frame=live_frame(midi=40))
        view._pluck_detector = FakePluckDetector(
            pluck=SimpleNamespace(midi=40, confidence=0.95, note_name="E2")
        )

        view._update_frame()

        after = view._controller.snapshot()
        self.assertEqual(before.current_index, after.current_index)
        self.assertEqual(after.passed_count, 0)
        self.assertIn("E2", view.detected_label.text())
        self.assertEqual(view.status_label.text(), "Detected E2 while paused.")
        view.close()

    def test_learn_input_starts_from_selected_device(self):
        devices = [
            AudioDevice(index=3, name="Laptop Mic", input_channels=1, default_sample_rate=48000),
            AudioDevice(index=7, name="USB Guitar", input_channels=1, default_sample_rate=48000),
        ]
        fake_input = FakeInput(frame=None)
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ), patch("interfaces.learn.view.list_input_devices", return_value=devices), patch(
            "interfaces.learn.view.LivePitchInput",
            return_value=fake_input,
        ):
            view = LearnView()

        view.device_combo.setCurrentIndex(1)
        view.start_input()

        self.assertEqual(fake_input.started_device_index, 7)
        self.assertTrue(view._running)
        self.assertEqual(view.status_label.text(), "Listening.")
        view.close()

    def _multi_track_song(self) -> LearnSong:
        target_events = [MidiNoteEvent(0.0, 0.5, 40, 1.0, 0)]
        context_events = [MidiNoteEvent(0.0, 1.0, 45, 1.0, 1)]
        target_section = section_from_targets(group_note_events(target_events))
        context_section = section_from_targets(group_note_events(context_events))
        return LearnSong(
            title="Test Song",
            path=None,
            tracks=[
                MidiTrackOption(
                    index=1,
                    name="Target",
                    channel_labels=("1",),
                    section=target_section,
                    notes=(MidiNoteSpan(0.0, 0.5, 40, 1.0, 0),),
                    color="#21d4fd",
                ),
                MidiTrackOption(
                    index=2,
                    name="Context",
                    channel_labels=("2",),
                    section=context_section,
                    notes=(MidiNoteSpan(0.0, 1.0, 45, 1.0, 1),),
                    color="#ff4d4d",
                ),
            ],
        )

    def _detuned_song(self) -> LearnSong:
        target_events = [MidiNoteEvent(0.0, 0.5, 38, 1.0, 0)]
        target_section = section_from_targets(group_note_events(target_events))
        return LearnSong(
            title="Detuned Test Song",
            path=None,
            tracks=[
                MidiTrackOption(
                    index=1,
                    name="Detuned Target",
                    channel_labels=("1",),
                    section=target_section,
                    notes=(MidiNoteSpan(0.0, 0.5, 38, 1.0, 0),),
                    color="#21d4fd",
                ),
            ],
        )


class FakeInput:
    def __init__(self, frame):
        self.frame = frame
        self.started_device_index = None
        self.sample_rate = 48000

    def start(self, device_index):
        self.started_device_index = device_index

    def latest_frame(self):
        return self.frame

    def stop(self):
        pass


class FakePluckDetector:
    def __init__(self, pluck):
        self.pluck = pluck
        self.current_pluck = None

    def process_frame(self, frame, now):
        if self.pluck is not None:
            self.current_pluck = self.pluck
        return self.pluck


def live_frame(midi: int | None):
    peak = None
    if midi is not None:
        peak = SimpleNamespace(
            midi=midi,
            frequency_hz=82.41,
            harmonic_relationship="fundamental",
        )
    return SimpleNamespace(
        likely_fundamental=peak,
        dominant_peak=peak,
        peaks=(peak,) if peak is not None else (),
    )


if __name__ == "__main__":
    unittest.main()
