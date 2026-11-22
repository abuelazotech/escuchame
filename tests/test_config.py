import unittest

from control_voz.config import _normalize_commands, _normalize_dictionary


class TestConfig(unittest.TestCase):
    def test_normalize_commands_filters_invalid(self):
        cmds = _normalize_commands([
            {"phrase": "abrir", "action": "run", "value": "x", "enabled": True},
            {"phrase": "", "action": "run", "value": "x"},
            {"phrase": "malo", "action": "hack", "value": "x"},
        ])
        self.assertEqual(cmds, [{"phrase": "abrir", "action": "run", "value": "x", "enabled": True}])

    def test_normalize_dictionary_dedup(self):
        words = _normalize_dictionary(["Hola", " hola ", "", "Mundo"])
        self.assertEqual(words, ["Hola", "Mundo"])


if __name__ == "__main__":
    unittest.main()
