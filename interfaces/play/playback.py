"""Single-clock transport policy for the Play MIDI viewer."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class PlaybackState:
    """Current transport state expressed in source-MIDI seconds."""

    position: float
    duration: float
    is_playing: bool


class PlaybackController:
    """Own Play's authoritative position independently of Qt and FluidSynth.

    Audio is rendered from this position whenever playback starts or resumes;
    therefore the UI never maintains a second, competing playback clock.
    """

    def __init__(self, duration: float = 0.0) -> None:
        self._duration = max(0.0, float(duration))
        self._position = 0.0
        self._is_playing = False
        self._started_at: float | None = None

    def load(self, duration: float) -> PlaybackState:
        """Load a song duration and reset its transport to the beginning."""

        self._duration = max(0.0, float(duration))
        self._position = 0.0
        self._is_playing = False
        self._started_at = None
        return self.snapshot()

    def play(self, now: float) -> PlaybackState:
        """Start or resume at the current source-MIDI position."""

        self.update(now)
        if self._position >= self._duration:
            self._position = 0.0
        if self._duration > 0.0:
            self._is_playing = True
            self._started_at = float(now)
        return self.snapshot()

    def pause(self, now: float) -> PlaybackState:
        """Freeze the transport at its current source-MIDI position."""

        self.update(now)
        self._is_playing = False
        self._started_at = None
        return self.snapshot()

    def restart(self) -> PlaybackState:
        """Return to the beginning without automatically starting audio."""

        self._position = 0.0
        self._is_playing = False
        self._started_at = None
        return self.snapshot()

    def update(self, now: float) -> PlaybackState:
        """Advance the sole transport clock and stop at the song end."""

        if not self._is_playing or self._started_at is None:
            return self.snapshot()
        self._position = min(self._duration, self._position + max(0.0, float(now) - self._started_at))
        self._started_at = float(now)
        if self._position >= self._duration:
            self._is_playing = False
            self._started_at = None
        return self.snapshot()

    def snapshot(self) -> PlaybackState:
        """Return the current state without advancing time."""

        return PlaybackState(self._position, self._duration, self._is_playing)
