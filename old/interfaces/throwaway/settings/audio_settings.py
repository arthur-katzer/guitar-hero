"""Audio settings placeholder panel."""

from __future__ import annotations

from interfaces.throwaway.shared.cards import Card, muted_label
from interfaces.throwaway.shared.controls import LabeledCombo, LabeledFloatSpin, LabeledSpin
from interfaces.throwaway.shared.models import AudioStatus


class AudioSettings(Card):
    """Mock audio settings for future device integration.

    @author Codex - created for the PySide6 GUI scaffold.
    """

    def __init__(self, audio_status: AudioStatus, parent=None):
        super().__init__("Audio settings", "Future input-device configuration", parent=parent)
        self.layout.addWidget(
            LabeledCombo(
                "Input device",
                [audio_status.input_device, "System audio placeholder", "USB interface placeholder"],
                enabled=False,
            )
        )
        self.layout.addWidget(LabeledSpin("Sample rate", audio_status.sample_rate, enabled=False))
        self.layout.addWidget(LabeledSpin("Buffer size", audio_status.buffer_size, enabled=False))
        self.layout.addWidget(
            LabeledFloatSpin("RMS threshold", audio_status.rms_threshold, maximum=1.0, enabled=False)
        )
        self.layout.addWidget(
            LabeledCombo(
                "Pitch mode",
                [audio_status.pitch_mode, "Dominant peak", "Chroma"],
                enabled=False,
            )
        )
        self.layout.addWidget(muted_label("No sounddevice stream is opened by the scaffold."))
        self.layout.addStretch(1)

