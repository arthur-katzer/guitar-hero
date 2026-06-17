import unittest

from audio.device_select import find_system_audio_device, normalize_device_name, parse_device


class FakeSoundDevice:
    def __init__(self, devices):
        self._devices = devices

    def query_devices(self):
        return self._devices


class DeviceSelectTests(unittest.TestCase):
    def test_parse_device_converts_indexes(self):
        self.assertEqual(parse_device("19"), 19)
        self.assertEqual(parse_device("Stereo Mix"), "Stereo Mix")
        self.assertIsNone(parse_device(None))

    def test_normalize_device_name_removes_portuguese_accents(self):
        self.assertEqual(normalize_device_name("Mixagem estéreo"), "mixagem estereo")

    def test_find_system_audio_device_prefers_stereo_mix_input(self):
        fake = FakeSoundDevice(
            [
                {"name": "Microfone", "max_input_channels": 2},
                {"name": "Alto-falantes", "max_input_channels": 0},
                {"name": "Mixagem estéreo", "max_input_channels": 2},
            ]
        )
        self.assertEqual(find_system_audio_device(fake), 2)

    def test_find_system_audio_device_returns_none_when_missing(self):
        fake = FakeSoundDevice([{"name": "Microfone", "max_input_channels": 2}])
        self.assertIsNone(find_system_audio_device(fake))


if __name__ == "__main__":
    unittest.main()
