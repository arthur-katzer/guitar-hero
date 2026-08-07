from interfaces.play.playback import PlaybackController


def test_transport_pauses_and_resumes_from_one_position() -> None:
    transport = PlaybackController(10.0)

    assert transport.play(100.0).is_playing
    assert transport.update(103.5).position == 3.5
    paused = transport.pause(104.0)
    assert paused.position == 4.0
    assert transport.update(120.0).position == 4.0
    assert transport.play(120.0).is_playing
    assert transport.update(122.0).position == 6.0


def test_transport_stops_at_end_and_restart_resets_it() -> None:
    transport = PlaybackController(2.0)

    transport.play(0.0)
    ended = transport.update(3.0)
    assert ended.position == 2.0
    assert not ended.is_playing
    assert transport.restart().position == 0.0
