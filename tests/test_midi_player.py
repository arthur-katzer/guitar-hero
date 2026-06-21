import unittest
import tempfile
from pathlib import Path

import mido

from interfaces.audio.midi_rendering import FilteredMidiRenderer, FilteredMidiRenderRequest
from interfaces.audio.midi_player import FluidSynthMidiPlayer, FluidSynthSettings


class FakeProcess:
    def __init__(self):
        self.terminated = False

    def terminate(self):
        self.terminated = True


class FakeSleeper:
    def __init__(self):
        self.calls = []

    def sleep(self, seconds):
        self.calls.append(seconds)


class MidiPlayerTests(unittest.TestCase):
    def test_builds_old_fluidsynth_command_as_reusable_adapter(self):
        player = FluidSynthMidiPlayer(
            FluidSynthSettings(
                soundfont_path=Path("/sound.sf2"),
                audio_driver="alsa",
                gain=1.25,
                executable="fluidsynth",
            )
        )

        command = player.command_for(Path("song.mid"))

        self.assertEqual(
            command,
            ["fluidsynth", "-a", "alsa", "-g", "1.25", "/sound.sf2", "song.mid"],
        )

    def test_play_starts_process_and_applies_warmup_without_real_audio(self):
        process = FakeProcess()
        calls = []
        sleeper = FakeSleeper()

        def factory(command, *, stdout, stderr):
            calls.append((command, stdout, stderr))
            return process

        player = FluidSynthMidiPlayer(
            FluidSynthSettings(soundfont_path=Path("/sound.sf2"), warmup_seconds=0.3),
            process_factory=factory,
            sleeper=sleeper,
        )

        player.play(Path("song.mid"))

        self.assertTrue(player.is_playing)
        self.assertEqual(calls[0][0], ["fluidsynth", "-a", "pulseaudio", "-g", "2.0", "/sound.sf2", "song.mid"])
        self.assertEqual(sleeper.calls, [0.3])
        self.assertFalse(process.terminated)

    def test_stop_terminates_only_active_process(self):
        first = FakeProcess()
        second = FakeProcess()
        processes = [first, second]

        def factory(command, *, stdout, stderr):
            return processes.pop(0)

        player = FluidSynthMidiPlayer(
            FluidSynthSettings(soundfont_path=Path("/sound.sf2"), warmup_seconds=0.0),
            process_factory=factory,
        )

        player.play(Path("first.mid"))
        player.play(Path("second.mid"))
        player.stop()
        player.stop()

        self.assertTrue(first.terminated)
        self.assertTrue(second.terminated)
        self.assertFalse(player.is_playing)

    def test_filtered_renderer_excludes_tracks_not_selected_for_playback(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mid"
            output = Path(tmp_dir) / "filtered.mid"
            self._write_two_track_midi(source)

            FilteredMidiRenderer().render(
                FilteredMidiRenderRequest(
                    source_path=source,
                    output_path=output,
                    track_indexes=frozenset({1}),
                    start_time=0.0,
                    end_time=2.0,
                    speed=1.0,
                )
            )

            self.assertEqual(self._note_on_numbers(output), [40])

    def test_filtered_renderer_applies_region_and_speed_to_output_ticks(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            source = Path(tmp_dir) / "source.mid"
            output = Path(tmp_dir) / "filtered.mid"
            self._write_two_track_midi(source)

            FilteredMidiRenderer().render(
                FilteredMidiRenderRequest(
                    source_path=source,
                    output_path=output,
                    track_indexes=frozenset({2}),
                    start_time=0.5,
                    end_time=1.5,
                    speed=2.0,
                )
            )

            self.assertEqual(self._note_on_numbers(output), [45])
            self.assertEqual(self._note_event_ticks(output), [(0, "note_on", 45), (480, "note_off", 45)])

    def _write_two_track_midi(self, midi_path: Path) -> None:
        mid = mido.MidiFile(type=1, ticks_per_beat=480)

        conductor = mido.MidiTrack()
        conductor.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
        mid.tracks.append(conductor)

        target = mido.MidiTrack()
        target.append(mido.MetaMessage("track_name", name="TARGET", time=0))
        target.append(mido.Message("note_on", note=40, velocity=80, channel=0, time=0))
        target.append(mido.Message("note_off", note=40, velocity=0, channel=0, time=480))
        mid.tracks.append(target)

        accompaniment = mido.MidiTrack()
        accompaniment.append(mido.MetaMessage("track_name", name="ACCOMP", time=0))
        accompaniment.append(mido.Message("note_on", note=45, velocity=80, channel=1, time=480))
        accompaniment.append(mido.Message("note_off", note=45, velocity=0, channel=1, time=960))
        mid.tracks.append(accompaniment)

        mid.save(midi_path)

    def _note_on_numbers(self, midi_path: Path) -> list[int]:
        notes = []
        for _tick, event_type, note in self._note_event_ticks(midi_path):
            if event_type == "note_on":
                notes.append(note)
        return notes

    def _note_event_ticks(self, midi_path: Path) -> list[tuple[int, str, int]]:
        midi_file = mido.MidiFile(str(midi_path))
        events: list[tuple[int, str, int]] = []
        for track in midi_file.tracks:
            absolute_tick = 0
            for message in track:
                absolute_tick += int(message.time)
                if message.type == "note_on" and message.velocity > 0:
                    events.append((absolute_tick, "note_on", int(message.note)))
                elif message.type == "note_off" or (message.type == "note_on" and message.velocity == 0):
                    events.append((absolute_tick, "note_off", int(message.note)))
        return events


if __name__ == "__main__":
    unittest.main()
