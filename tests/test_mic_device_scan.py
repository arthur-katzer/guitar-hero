import unittest

import numpy as np

from mic_device_scan import classify_signal, to_mono


class MicDeviceScanTests(unittest.TestCase):
    def test_classify_signal(self):
        self.assertEqual(classify_signal(rms=0.0, peak=0.0, threshold=0.005), "digital_silence")
        self.assertEqual(classify_signal(rms=0.002, peak=0.02, threshold=0.005), "very_quiet")
        self.assertEqual(classify_signal(rms=0.2, peak=0.99, threshold=0.005), "clipping_risk")
        self.assertEqual(classify_signal(rms=0.02, peak=0.2, threshold=0.005), "usable_signal")

    def test_to_mono_averages_channels(self):
        stereo = np.asarray([[1.0, -1.0], [0.5, 0.0]], dtype=np.float32)
        mono = to_mono(stereo)
        np.testing.assert_allclose(mono, [0.0, 0.25])


if __name__ == "__main__":
    unittest.main()
