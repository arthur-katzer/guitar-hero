import importlib


def test_root_audio_pitch_detector_delegates_to_cli_main():
    module = importlib.import_module("audio_pitch_detector")
    cli = importlib.import_module("audio_detection.cli.audio_pitch_detector")

    assert module.main is cli.main
