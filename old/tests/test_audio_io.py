import tempfile
import unittest
from pathlib import Path

import numpy as np
from scipy.io import wavfile

from audio.io import load_audio


class AudioIoTests(unittest.TestCase):
    def test_load_audio_reads_wav_as_mono_float(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stereo.wav"
            samples = np.asarray([[32767, -32767], [16384, 0]], dtype=np.int16)
            wavfile.write(path, 44100, samples)

            audio, sample_rate = load_audio(path)

        self.assertEqual(sample_rate, 44100)
        self.assertEqual(audio.dtype, np.float32)
        self.assertEqual(audio.ndim, 1)
        np.testing.assert_allclose(audio, [0.0, 0.25], atol=1e-4)

    def test_load_audio_can_resample_wav(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "mono.wav"
            samples = np.zeros(44100, dtype=np.float32)
            wavfile.write(path, 44100, samples)

            audio, sample_rate = load_audio(path, sample_rate=22050)

        self.assertEqual(sample_rate, 22050)
        self.assertEqual(len(audio), 22050)


if __name__ == "__main__":
    unittest.main()
