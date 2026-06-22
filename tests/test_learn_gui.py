import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from interfaces import theme
from interfaces.audio.pitch import AudioDevice
from interfaces.gui.main_window import MainWindow
from interfaces.i18n import text
from interfaces.learn.midi_targets import MidiNoteEvent, group_note_events, section_from_targets
from interfaces.learn.model import LearnSong, MidiNoteSpan, MidiTrackOption
from interfaces.learn.view import LearnView, MidiOverviewBar, PianoRollTimeline
from interfaces.sandbox.view import SandboxView


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

    def test_main_menu_hides_and_disables_play_mode(self):
        with patch("interfaces.learn.view.list_input_devices", return_value=[]), patch(
            "interfaces.sandbox.view.list_input_devices",
            return_value=[],
        ):
            window = MainWindow()

            self.assertEqual([button.text() for button in window.menu.buttons], [text("menu.learn"), text("menu.sandbox")])
            self.assertFalse(hasattr(window, "play"))

            window._open_option("Play")

            self.assertIs(window.screens.currentWidget(), window.background)
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

    def test_learn_view_auto_selects_clear_guitar_track_in_multi_track_song(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_guitar_song(),
        ):
            view = LearnView()

        state = view._controller.snapshot()
        self.assertEqual(view._target_track.name, "Clean Guitar")
        self.assertEqual(state.selected_count, 1)
        self.assertEqual(state.current_target.midi_notes, [45])
        self.assertTrue(view._target_radios[2].isChecked())
        view.close()

    def test_overview_controls_display_window_without_changing_practice_region(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        self.assertIsInstance(view.timeline_overview, MidiOverviewBar)
        view._select_target_track(1)
        practice_region = view._controller.region

        view._set_display_window(0.25, 0.75)

        start_time, end_time = view.timeline._timeline_bounds()
        self.assertAlmostEqual(start_time, 0.25)
        self.assertAlmostEqual(end_time, 0.75)
        self.assertAlmostEqual(view.timeline_overview._display_window.start_time, 0.25)
        self.assertAlmostEqual(view.timeline_overview._display_window.end_time, 0.75)
        self.assertEqual(view._controller.region, practice_region)
        view.close()

    def test_run_mode_controls_are_not_present(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._long_song(),
        ):
            view = LearnView()

        self.assertFalse(hasattr(view, "mode_combo"))
        self.assertFalse(hasattr(view, "play_button"))
        self.assertFalse(hasattr(view, "speed_combo"))
        self.assertFalse(hasattr(view, "count_in_combo"))
        self.assertFalse(hasattr(view, "loop_check"))
        self.assertFalse(hasattr(view, "playhead_bar"))
        self.assertTrue(hasattr(view, "reset_button"))
        self.assertFalse(hasattr(view, "suggest_transpose_button"))
        view.close()

    def test_reset_button_clears_learn_progress_without_changing_target_track(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._long_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        view._controller.start(0.0)
        view._controller.process_detected_note(40, confidence=0.95)

        view.reset_button.click()

        state = view._controller.snapshot()
        self.assertEqual(state.passed_count, 0)
        self.assertEqual(state.current_index, 0)
        self.assertEqual(state.current_target.midi_notes, [40])
        self.assertEqual(view._target_track.index, 1)
        self.assertEqual(view.status_label.text(), text("learn.reset_done"))
        view.close()

    def test_learn_timeline_playhead_tracks_current_target(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._long_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        self.assertAlmostEqual(view.timeline._playhead_time, 0.0)

        view._controller.start(0.0)
        state = view._controller.process_detected_note(40, confidence=0.95)
        view._render_state(state)

        self.assertAlmostEqual(view.timeline._playhead_time, 5.5)
        self.assertEqual(view._controller.snapshot().current_target.midi_notes, [45])
        view.close()

    def test_overview_background_click_does_not_steal_display_handle_drag(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._long_song(),
        ):
            view = LearnView()

        view.timeline_overview.resize(800, 72)
        view._set_display_window(0.0, 2.0)
        before = view.timeline_overview._display_window
        view.timeline_overview.mousePressEvent(FakeMouseEvent(650, 36))
        view.timeline_overview.mouseMoveEvent(FakeMouseEvent(700, 36))

        self.assertIsNone(view.timeline_overview._dragging)
        self.assertEqual(view.timeline_overview._display_window, before)
        view.close()

    def test_overview_body_drag_pans_display_window_without_resizing(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._long_song(),
        ):
            view = LearnView()

        view.timeline_overview.resize(800, 72)
        view._set_display_window(1.0, 3.0)
        before = view.timeline_overview._display_window

        view.timeline_overview.mousePressEvent(FakeMouseEvent(310, 36))
        view.timeline_overview.mouseMoveEvent(FakeMouseEvent(410, 36))

        after = view.timeline_overview._display_window
        self.assertEqual(view.timeline_overview._dragging, "body")
        self.assertGreater(after.start_time, before.start_time)
        self.assertAlmostEqual(after.end_time - after.start_time, before.end_time - before.start_time)
        self.assertEqual(view.timeline._timeline_bounds(), (after.start_time, after.end_time))
        view.close()

    def test_transpose_control_updates_labels_matching_and_range_warning(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._detuned_song(),
        ):
            view = LearnView()

        self.assertEqual(view.transpose_spin.minimum(), -12)
        self.assertEqual(view.transpose_spin.maximum(), 12)
        self.assertEqual(view.transpose_down_button.text(), "-")
        self.assertEqual(view.transpose_up_button.text(), "+")
        self.assertEqual(view.transpose_value_label.text(), "0")
        self.assertIs(view.lowest_note_label.parent(), view.transpose_panel)
        self.assertIs(view.highest_note_label.parent(), view.transpose_panel)
        self.assertEqual(view._controller.snapshot().current_target.midi_notes, [38])
        self.assertEqual(view.lowest_note_label.text(), text("learn.lowest_note", note="D2"))
        self.assertEqual(view.highest_note_label.text(), text("learn.highest_note", note="D2"))
        self.assertEqual(view.lowest_note_label.property("rangeState"), "warning")
        self.assertEqual(view.highest_note_label.property("rangeState"), "normal")
        self.assertEqual(view.range_warning_label.text(), "")

        view.transpose_up_button.click()
        view.transpose_up_button.click()

        state = view._controller.snapshot()
        self.assertEqual(state.current_target.original_midi_notes, [38])
        self.assertEqual(state.current_target.midi_notes, [40])
        self.assertEqual(view.current_target_label.text(), "E2 (82.4 Hz)")
        self.assertIn("[ ] E2 (82.4 Hz)", view.expected_label.text())
        self.assertIn("D2 -> E2", view.transpose_preview_label.text())
        self.assertEqual(view.transpose_value_label.text(), "+2")
        self.assertEqual(view.lowest_note_label.text(), text("learn.lowest_note", note="E2"))
        self.assertEqual(view.highest_note_label.text(), text("learn.highest_note", note="E2"))
        self.assertEqual(view.lowest_note_label.property("rangeState"), "normal")
        self.assertEqual(view.highest_note_label.property("rangeState"), "normal")
        self.assertEqual(view.range_warning_label.text(), "")
        self.assertEqual(view._target_track.section.targets[0].midi_notes, [38])
        self.assertEqual(view.timeline._transpose_semitones, 2)

        view.transpose_down_button.click()
        self.assertEqual(view.transpose_spin.value(), 1)
        self.assertEqual(view.transpose_value_label.text(), "+1")
        view.close()

    def test_visible_track_control_changes_only_timeline_visibility(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        view._set_track_visible(2, False)

        self.assertNotIn(2, view.timeline._visible_track_indexes)
        self.assertEqual(view._controller.snapshot().current_target.midi_notes, [40])
        self.assertFalse(hasattr(view, "_set_track_audible"))
        self.assertFalse(hasattr(view, "_set_track_solo"))
        view.close()

    def test_side_rail_switches_between_practice_readouts_and_tracks(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        selected_before = view._controller.snapshot().current_target

        self.assertEqual(view.side_stack.currentIndex(), 0)
        self.assertTrue(view.practice_view_button.isChecked())
        view._show_tracks_panel()

        self.assertEqual(view.side_stack.currentIndex(), 1)
        self.assertTrue(view.tracks_view_button.isChecked())
        self.assertIs(view._controller.snapshot().current_target, selected_before)

        view._show_practice_panel()

        self.assertEqual(view.side_stack.currentIndex(), 0)
        self.assertTrue(view.practice_view_button.isChecked())
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

        self.assertEqual(view.status_label.text(), text("input.listening"))
        self.assertIn("E2", view.detected_label.text())
        view.close()

    def test_update_frame_advances_wait_practice_without_play_button(self):
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ):
            view = LearnView()

        view._select_target_track(1)
        view._input = FakeInput(frame=live_frame(midi=40))
        view._pluck_detector = FakePluckDetector(
            pluck=SimpleNamespace(midi=40, confidence=0.95, note_name="E2")
        )

        view._update_frame()

        after = view._controller.snapshot()
        self.assertEqual(after.passed_count, 1)
        self.assertIn("E2", view.detected_label.text())
        self.assertEqual(view.status_label.text(), text("learn.detected_note", note="E2"))
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
        self.assertEqual(view.status_label.text(), text("input.listening"))
        view.close()

    def test_input_button_uses_accessible_shape_states(self):
        devices = [AudioDevice(index=7, name="USB Guitar", input_channels=1, default_sample_rate=48000)]
        fake_input = FakeInput(frame=None)
        with patch("interfaces.learn.view.discover_midi_songs", return_value=[]), patch(
            "interfaces.learn.view.demo_song",
            return_value=self._multi_track_song(),
        ), patch("interfaces.learn.view.list_input_devices", return_value=devices), patch(
            "interfaces.learn.view.LivePitchInput",
            return_value=fake_input,
        ):
            view = LearnView()

        self.assertEqual(view.start_button.text(), "")
        self.assertEqual(view.start_button.property("inputState"), "stopped")
        self.assertEqual(view.start_button.toolTip(), text("input.start"))

        view.start_input()

        self.assertEqual(view.start_button.text(), "")
        self.assertEqual(view.start_button.property("inputState"), "running")
        self.assertEqual(view.start_button.toolTip(), text("input.stop"))

        view.stop_input()

        self.assertEqual(view.start_button.text(), "")
        self.assertEqual(view.start_button.property("inputState"), "stopped")
        self.assertEqual(view.start_button.toolTip(), text("input.start"))
        view.close()

    def test_sandbox_input_button_uses_same_shape_states(self):
        devices = [AudioDevice(index=7, name="USB Guitar", input_channels=1, default_sample_rate=48000)]
        fake_input = FakeInput(frame=None)
        with patch("interfaces.sandbox.view.list_input_devices", return_value=devices), patch(
            "interfaces.sandbox.view.LivePitchInput",
            return_value=fake_input,
        ), patch("interfaces.sandbox.view.QTimer.singleShot"):
            view = SandboxView()

        self.assertEqual(view.start_button.text(), "")
        self.assertEqual(view.start_button.property("inputState"), "stopped")
        self.assertEqual(view.start_button.toolTip(), text("input.start"))

        view.start_input()

        self.assertEqual(view.start_button.text(), "")
        self.assertEqual(view.start_button.property("inputState"), "running")
        self.assertEqual(view.start_button.toolTip(), text("input.stop"))

        view.stop_input()

        self.assertEqual(view.start_button.text(), "")
        self.assertEqual(view.start_button.property("inputState"), "stopped")
        self.assertEqual(view.start_button.toolTip(), text("input.start"))
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
                    color=theme.TRACK_COLORS[0],
                ),
                MidiTrackOption(
                    index=2,
                    name="Context",
                    channel_labels=("2",),
                    section=context_section,
                    notes=(MidiNoteSpan(0.0, 1.0, 45, 1.0, 1),),
                    color=theme.TRACK_COLORS[1],
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
                    color=theme.TRACK_COLORS[0],
                ),
            ],
        )

    def _long_song(self) -> LearnSong:
        target_events = [
            MidiNoteEvent(0.0, 0.5, 40, 1.0, 0),
            MidiNoteEvent(5.5, 6.0, 45, 1.0, 0),
        ]
        target_section = section_from_targets(group_note_events(target_events))
        return LearnSong(
            title="Long Test Song",
            path=None,
            tracks=[
                MidiTrackOption(
                    index=1,
                    name="Long Target",
                    channel_labels=("1",),
                    section=target_section,
                    notes=(
                        MidiNoteSpan(0.0, 0.5, 40, 1.0, 0),
                        MidiNoteSpan(5.5, 6.0, 45, 1.0, 0),
                    ),
                    color=theme.TRACK_COLORS[0],
                ),
            ],
        )

    def _multi_track_guitar_song(self) -> LearnSong:
        piano_events = [MidiNoteEvent(0.0, 0.5, 60, 1.0, 0)]
        guitar_events = [MidiNoteEvent(0.0, 0.5, 45, 1.0, 1)]
        piano_section = section_from_targets(group_note_events(piano_events))
        guitar_section = section_from_targets(group_note_events(guitar_events))
        return LearnSong(
            title="Guitar Track Test Song",
            path=None,
            tracks=[
                MidiTrackOption(
                    index=1,
                    name="Electric Piano",
                    channel_labels=("1",),
                    section=piano_section,
                    notes=(MidiNoteSpan(0.0, 0.5, 60, 1.0, 0),),
                    color=theme.TRACK_COLORS[0],
                ),
                MidiTrackOption(
                    index=2,
                    name="Clean Guitar",
                    channel_labels=("2",),
                    section=guitar_section,
                    notes=(MidiNoteSpan(0.0, 0.5, 45, 1.0, 1),),
                    color=theme.TRACK_COLORS[1],
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


class FakeMouseEvent:
    def __init__(self, x, y):
        self._point = SimpleNamespace(x=lambda: x, y=lambda: y)

    def pos(self):
        return self._point


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
