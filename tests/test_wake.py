import os
import tempfile
import unittest
from unittest import mock

from control_voz.engine import VoiceEngine
from control_voz.wake import SLEEP, WAKE, detect_wake


class TestDetectWake(unittest.TestCase):
    def test_detect_wake_and_sleep(self):
        cases = [
            ("escúchame", WAKE),
            ("Escucha me, por favor", WAKE),
            ("buenos días escúchame", WAKE),
            ("ensordece", SLEEP),
            ("En sordece ya", SLEEP),
            ("buenos días", None),
            ("escucha", None),
            ("ensordecer", None),
            ("", None),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(detect_wake(text), expected)


class TestEngineWake(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()
        self.events = []

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def engine(self, **config):
        return VoiceEngine({"state": "off", "wake_word_enabled": True, **config}, self.events.append)

    def test_wake_activates_command_and_emits_popup_event(self):
        engine = self.engine()
        engine._handle_wake(WAKE)
        self.assertEqual(engine.state, "command")
        self.assertEqual([event.kind for event in self.events], ["state", "wake"])

    def test_sleep_works_from_dictation(self):
        engine = self.engine()
        engine.set_state("dictation")
        self.events.clear()
        engine._handle_wake(SLEEP)
        self.assertEqual(engine.state, "off")
        self.assertEqual([event.kind for event in self.events], ["state", "sleep"])

    def test_wake_word_enabled_can_be_disabled(self):
        self.assertFalse(self.engine(wake_word_enabled=False).wake_word_enabled)


if __name__ == "__main__":
    unittest.main()
