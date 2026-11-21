import unittest
from struct import pack
from unittest.mock import patch

import webrtcvad

from auto_c import VoiceGate


RATE = 16000
SAMPLES = RATE // 50  # 20 ms of mono PCM


def frame(amplitude):
    cycle = pack('<hh', amplitude, -amplitude)
    return cycle * (SAMPLES // 2)


LOUD = frame(4096)
QUIET = frame(32)
SILENCE = frame(0)


class VoiceGateTests(unittest.TestCase):
    def setUp(self):
        self.gate = VoiceGate(threshold_db=-45.0, release_ms=300)
        detector = patch.object(webrtcvad.Vad, 'is_speech', return_value=True)
        self.speech = detector.start()
        self.addCleanup(detector.stop)

    def open_gate(self):
        self.assertFalse(self.gate.update(LOUD, RATE))
        self.assertTrue(self.gate.update(LOUD, RATE))

    def test_needs_two_consecutive_qualifying_frames(self):
        self.assertFalse(self.gate.update(LOUD, RATE))
        self.speech.return_value = False
        for _ in range(3):
            self.assertFalse(self.gate.update(LOUD, RATE))
        self.speech.return_value = True
        self.open_gate()

    def test_quiet_frames_below_threshold_do_not_open_gate(self):
        for audio in (SILENCE, QUIET, QUIET, LOUD, QUIET):
            self.assertFalse(self.gate.update(audio, RATE))
        self.open_gate()

    def test_holds_across_short_pause_and_releases_after_full_pause(self):
        self.open_gate()
        for _ in range(10):
            self.assertTrue(self.gate.update(SILENCE, RATE))
        self.assertTrue(self.gate.update(LOUD, RATE))
        for _ in range(14):
            self.assertTrue(self.gate.update(SILENCE, RATE))
        self.assertFalse(self.gate.update(SILENCE, RATE))
        self.open_gate()

    def test_reset_discards_held_state_and_partial_onset(self):
        self.open_gate()
        self.gate.reset()
        self.assertFalse(self.gate.update(LOUD, RATE))
        self.gate.reset()
        self.open_gate()


if __name__ == '__main__':
    unittest.main()
