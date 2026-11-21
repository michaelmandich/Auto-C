import unittest
from contextlib import nullcontext
from struct import pack
from types import SimpleNamespace
from unittest.mock import patch

import auto_c


RATE = 16000
SAMPLES = RATE * auto_c.FRAME_MS // 1000
LOUD = pack("<hh", 16384, -16384) * (SAMPLES // 2)
SILENCE = bytes(2 * SAMPLES)


class FakeKey:
    def __init__(self, available=True, refuse_first=False):
        self.available = available
        self.refuse_first = refuse_first
        self.down_attempts = 0
        self.held = False

    def eligible(self):
        return self.available

    def set_down(self, down):
        if down:
            self.down_attempts += 1
        self.held = down and not (self.refuse_first and self.down_attempts == 1)


def replay(audio, key=None, get_threshold=None, is_enabled=lambda: True):
    """Deliver exactly one PCM frame before each monitor iteration."""
    frames = iter(audio)
    reports = []
    args = SimpleNamespace(device=None, threshold=-45, dry_run=key is None)
    with (
        patch.object(auto_c.sd, "query_devices", return_value={"index": 0, "name": "Test mic"}),
        patch.object(auto_c, "capture_rate", return_value=RATE),
        patch.object(auto_c.sd, "RawInputStream") as stream,
        patch.object(auto_c.webrtcvad.Vad, "is_speech", return_value=True),
        patch.object(auto_c, "live_session", nullcontext),
        patch.object(auto_c, "LeagueKey", return_value=key) as create_key,
    ):
        def stopping():
            frame = next(frames, None)
            if frame is None:
                return True
            stream.call_args.kwargs["callback"](frame, SAMPLES, None, False)
            return False

        auto_c.listen(args, stopping, lambda state, dbfs: reports.append((state, dbfs)),
                      get_threshold=get_threshold, is_enabled=is_enabled)
        stream.assert_called_once()
        stream.return_value.__enter__.assert_called_once_with()
        if args.dry_run:
            create_key.assert_not_called()
    return reports


class MonitorStatusTests(unittest.TestCase):
    def test_meter_tracks_input_while_key_is_busy(self):
        key = FakeKey(available=False)
        reports = replay([SILENCE, LOUD, LOUD], key)
        self.assertEqual([state for state, _ in reports], ["key_busy"] * 3)
        self.assertEqual(reports[0][1], -96)
        self.assertAlmostEqual(reports[1][1], -6.02, places=2)
        self.assertEqual(key.down_attempts, 0)

    def test_live_starts_off_without_enable_callback_and_still_reports_levels(self):
        key = FakeKey()
        reports = replay([SILENCE, LOUD, LOUD], key, is_enabled=None)
        self.assertEqual([state for state, _ in reports], ["off"] * 3)
        self.assertEqual(reports[0][1], -96)
        self.assertAlmostEqual(reports[1][1], -6.02, places=2)
        self.assertEqual(key.down_attempts, 0)

    def test_switch_releases_immediately_and_requires_fresh_speech_when_reenabled(self):
        key = FakeKey()
        enabled = False
        held = []

        def audio():
            nonlocal enabled
            for enabled, frames in [(False, [LOUD] * 2), (True, [LOUD] * 2),
                                    (False, [LOUD]), (True, [LOUD] * 2 + [SILENCE] * 15)]:
                for frame in frames:
                    yield frame
                    held.append(key.held)

        reports = replay(audio(), key, is_enabled=lambda: enabled)
        expected = (["off", "off", "ready", "key_down", "off", "ready"] +
                    ["key_down"] * 15 + ["ready"])
        self.assertEqual([state for state, _ in reports], expected)
        self.assertEqual(held, [state == "key_down" for state in expected])

    def test_reports_only_successful_hold_and_releases_it_on_stop(self):
        key = FakeKey(refuse_first=True)
        reports = replay([LOUD, LOUD, LOUD], key)
        self.assertEqual([state for state, _ in reports], ["ready", "ready", "key_down"])
        self.assertEqual(key.down_attempts, 2)
        self.assertFalse(key.held)

    def test_threshold_changes_while_listening_with_constant_input(self):
        threshold = -3

        def audio():
            nonlocal threshold
            # LOUD stays at -6 dBFS throughout these three threshold settings.
            for threshold, frames in [(-3, 4), (-15, 2), (-3, 15)]:
                yield from [LOUD] * frames

        reports = replay(audio(), FakeKey(), get_threshold=lambda: threshold)
        self.assertEqual([state for state, _ in reports],
                         ["ready"] * 5 + ["key_down"] * 15 + ["ready"])

    def test_dry_run_reports_speech_and_quiet_without_creating_a_key(self):
        reports = replay([LOUD, LOUD] + [SILENCE] * 15, is_enabled=lambda: False)
        self.assertEqual([state for state, _ in reports],
                         ["test_quiet"] + ["test_speech"] * 15 + ["test_quiet"])


if __name__ == "__main__":
    unittest.main()
