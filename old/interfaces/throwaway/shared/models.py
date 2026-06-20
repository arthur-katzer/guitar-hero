"""Display models used by the PySide6 GUI scaffold.

These dataclasses are intentionally view-facing. They let the scaffold show the
future screens without importing audio capture, DSP, MIDI parsing, or scoring
policies.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Theme:
    """Normalized theme palette consumed by Qt widgets.

    The GUI depends on this small contract instead of the raw Monokai JSON or
    HTML formats so future theme sources can change without leaking into views.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    name: str
    kind: str
    colors: dict[str, str] = field(default_factory=dict)
    source: str = "built-in"


@dataclass(frozen=True)
class AudioStatus:
    """Mock input state for the desktop scaffold.

    The values are display placeholders only; real audio-device selection and
    capture remain outside the GUI adapter until that boundary is designed.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    input_device: str = "Mock Input Device"
    sample_rate: int = 48_000
    buffer_size: int = 1024
    rms_level: float = 0.42
    rms_threshold: float = 0.08
    pitch_mode: str = "Fundamental-aware"


@dataclass(frozen=True)
class PitchStatus:
    """Mock pitch state for tuner and trainer screens.

    Keeping these as simple display facts avoids placing detector rules inside
    widgets while the real audio-detection service boundary is still open.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    target_note: str = "A2"
    detected_note: str = "A2"
    frequency_hz: float = 110.0
    confidence: float = 0.91
    tuner_cents: int = -3
    trainer_state: str = "WAITING"
    harmonic_warning: str = "Harmonic check placeholder: no real detector wired."


@dataclass(frozen=True)
class GameStatus:
    """Mock rhythm-game state for the player screen.

    The model describes HUD values only. Real chart timing, hit windows, and
    scoring remain owned by the minigame runtime.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    song_title: str = "Mock Song - Standard Tuning Drill"
    difficulty: str = "Normal"
    current_target_note: str = "D3"
    detected_note: str = "D3"
    score: int = 12_450
    combo: int = 24
    accuracy: float = 96.4
    judgment: str = "GOOD"
    rms: float = 0.38
    confidence: float = 0.88
    pitch_mode: str = "Fundamental-aware"


@dataclass(frozen=True)
class GuitarString:
    """Standard tuning reference row shown by the tuner scaffold.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    note: str
    frequency_hz: float


STANDARD_TUNING: tuple[GuitarString, ...] = (
    GuitarString("E2", 82.41),
    GuitarString("A2", 110.00),
    GuitarString("D3", 146.83),
    GuitarString("G3", 196.00),
    GuitarString("B3", 246.94),
    GuitarString("E4", 329.63),
)

