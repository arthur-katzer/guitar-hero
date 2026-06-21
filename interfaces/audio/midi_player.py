"""MIDI playback adapter backed by FluidSynth.

The archived minigame played MIDI by spawning ``fluidsynth`` directly from its
engine. This module keeps that useful IO detail available without making game
or Learn policies depend on a process runner, soundfont path, or audio driver.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import subprocess
import time
from typing import Protocol


DEFAULT_SOUNDFONT_PATH = Path("/usr/share/soundfonts/FluidR3_GM.sf2")
DEFAULT_AUDIO_DRIVER = "pulseaudio"
DEFAULT_GAIN = 2.0
DEFAULT_WARMUP_SECONDS = 0.3


class MidiProcess(Protocol):
    """Process boundary needed by the MIDI player.

    Tests provide a small fake with this interface so playback policy can be
    verified without starting audio output on the developer machine.

    @author Codex - extracted MIDI process boundary from archived minigame.
    """

    def terminate(self) -> None:
        """Stop the underlying playback process.

        @author Codex - extracted MIDI process boundary from archived minigame.
        """


class MidiProcessFactory(Protocol):
    """Callable boundary for launching MIDI playback.

    @author Codex - extracted MIDI process boundary from archived minigame.
    """

    def __call__(
        self,
        command: list[str],
        *,
        stdout: int,
        stderr: int,
    ) -> MidiProcess:
        """Launch a process for ``command`` and return its handle.

        @author Codex - extracted MIDI process boundary from archived minigame.
        """


@dataclass(frozen=True)
class FluidSynthSettings:
    """Configuration for the FluidSynth MIDI adapter.

    These values are infrastructure choices. Keeping them in one value object
    prevents callers from rebuilding command-line details and leaves future
    playback backends free to use different settings.

    @author Codex - extracted FluidSynth MIDI settings from archived minigame.
    """

    soundfont_path: Path = DEFAULT_SOUNDFONT_PATH
    audio_driver: str = DEFAULT_AUDIO_DRIVER
    gain: float = DEFAULT_GAIN
    warmup_seconds: float = DEFAULT_WARMUP_SECONDS
    executable: str = "fluidsynth"


class FluidSynthMidiPlayer:
    """Play MIDI files through the external ``fluidsynth`` executable.

    MIDI rendering is an adapter concern: the application asks for a file to be
    played, while this class owns the process command and shutdown behavior.
    The old minigame implementation used the same backend, but embedded it in
    the runtime engine; this extraction keeps playback reusable by Play, Learn,
    or later song-library interfaces.

    @author Codex - extracted MIDI player from archived minigame.
    """

    def __init__(
        self,
        settings: FluidSynthSettings | None = None,
        *,
        process_factory: MidiProcessFactory = subprocess.Popen,
        sleeper: object = time,
    ) -> None:
        self._settings = settings or FluidSynthSettings()
        self._process_factory = process_factory
        self._sleeper = sleeper
        self._process: MidiProcess | None = None

    @property
    def is_playing(self) -> bool:
        """Return whether this adapter currently owns a playback process.

        @author Codex - extracted MIDI player state from archived minigame.
        """

        return self._process is not None

    def command_for(self, midi_path: Path) -> list[str]:
        """Build the FluidSynth command for ``midi_path``.

        Command creation is exposed for tests and diagnostics because failures
        here usually come from machine-level setup: missing FluidSynth,
        unavailable audio driver, or absent soundfont.

        @author Codex - extracted FluidSynth command from archived minigame.
        """

        return [
            self._settings.executable,
            "-a",
            self._settings.audio_driver,
            "-g",
            str(self._settings.gain),
            str(self._settings.soundfont_path),
            str(midi_path),
        ]

    def play(self, midi_path: Path) -> None:
        """Start playback for ``midi_path``, replacing any active playback.

        The adapter stops the previous process first so UI callers can treat a
        new song selection as a single command instead of coordinating process
        lifetime themselves.

        @author Codex - extracted MIDI playback behavior from archived minigame.
        """

        self.stop()
        command = self.command_for(midi_path)
        self._process = self._process_factory(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if self._settings.warmup_seconds > 0:
            self._sleeper.sleep(self._settings.warmup_seconds)

    def stop(self) -> None:
        """Stop active MIDI playback if this adapter started it.

        @author Codex - extracted MIDI stop behavior from archived minigame.
        """

        if self._process is None:
            return
        self._process.terminate()
        self._process = None

    def __enter__(self) -> FluidSynthMidiPlayer:
        """Return this player for scoped playback lifetimes.

        @author Codex - extracted MIDI player lifetime helper.
        """

        return self

    def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
        """Stop playback when leaving a scoped lifetime.

        @author Codex - extracted MIDI player lifetime helper.
        """

        self.stop()
