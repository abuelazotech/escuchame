import os
import tempfile
import unittest
from unittest import mock

from control_voz.actions import Command
from control_voz.config import config_dir
from control_voz.corrections import (
    add_correction,
    apply_corrections,
    apply_corrections_to_text,
    corrections_path,
    load_corrections,
    log_unknown,
    normalize_text,
    parse_correction,
)
from control_voz.engine import VoiceEngine


class TestCorrections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_normalize_text(self):
        self.assertEqual(normalize_text("¡CadenLAI, por favor!"), "cadenlai por favor")

    def test_parse_correction(self):
        self.assertEqual(parse_correction("corregir cadenlai es kdenlive"), ("cadenlai", "kdenlive"))
        self.assertEqual(parse_correction("Corrige: CadenLAI con Kdenlive"), ("cadenlai", "kdenlive"))
        self.assertEqual(parse_correction("corregir abrir el navegador por abrir firefox"),
                         ("abrir el navegador", "abrir firefox"))
        self.assertEqual(parse_correction("corregir cadenlai kdenlive"), ("cadenlai", "kdenlive"))
        self.assertIsNone(parse_correction("corregir"))
        self.assertIsNone(parse_correction("abrir terminal"))
        self.assertIsNone(parse_correction("corregir cadenlai es cadenlai"))

    def test_apply_corrections_uses_word_boundaries_and_longest_first(self):
        corrections = {"abrir": "lanzar", "abrir cadenlai": "abrir kdenlive"}
        self.assertEqual(apply_corrections("abrir cadenlai y abrir terminal", corrections),
                         "abrir kdenlive y lanzar terminal")
        self.assertEqual(apply_corrections("cadenlai", {"cadena": "otra"}), "cadenlai")

    def test_apply_corrections_to_text_preserves_case_and_accents(self):
        corrections = {"cadenlai": "kdenlive", "abrir el navegador": "abrir Firefox"}
        self.assertEqual(apply_corrections_to_text("Abrí cadenlai, por favor.", corrections),
                         "Abrí kdenlive, por favor.")
        self.assertEqual(apply_corrections_to_text("Quiero ABRIR EL NAVEGADOR ahora", corrections),
                         "Quiero abrir Firefox ahora")

    def test_add_and_load_corrections(self):
        add_correction("CadenLAI", "kdenlive")
        add_correction("cerral terminal", "cerrar terminal")
        add_correction("kdenlive", "kdenlive")
        self.assertEqual(load_corrections(), {
            "cadenlai": "kdenlive",
            "cerral terminal": "cerrar terminal",
        })
        self.assertEqual(corrections_path().read_text(encoding="utf-8"),
                         "cadenlai => kdenlive\ncerral terminal => cerrar terminal\n")

    def test_add_correction_overwrites_existing_key(self):
        add_correction("cadenlai", "kdenlive")
        add_correction("cadenlai", "kden live")
        self.assertEqual(load_corrections(), {"cadenlai": "kden live"})

    def test_log_unknown_appends_and_dedupes(self):
        log_unknown("con todo lo que hicimos hoy por favor")
        log_unknown("abrir cadenlai")
        log_unknown("abrir cadenlai")
        path = config_dir() / "no-reconocido.txt"
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read().splitlines(),
                             ["con todo lo que hicimos hoy por favor", "abrir cadenlai"])


class TestEngineCorrections(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()
        self.events = []
        self.config = {
            "commands": [
                {"phrase": "abrir kdenlive", "action": "run", "value": "kdenlive", "enabled": True},
            ],
        }
        self.engine = VoiceEngine(self.config, self.events.append)

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def test_correction_command_persists_and_applies(self):
        self.assertTrue(self.engine._handle_correction("corregir abrir cadenlai es abrir kdenlive"))
        self.assertEqual(load_corrections(), {"abrir cadenlai": "abrir kdenlive"})
        self.assertEqual([event.kind for event in self.events], ["correction"])
        commands = [Command(**item) for item in self.config["commands"]]
        with mock.patch("control_voz.engine.run_command", return_value="ok") as run:
            self.assertTrue(self.engine._handle_command("abrir cadenlai", commands))
        run.assert_called_once_with(commands[0])

    def test_unknown_command_is_logged(self):
        commands = [Command(**item) for item in self.config["commands"]]
        self.assertFalse(self.engine._handle_command("hacer algo raro", commands))
        path = config_dir() / "no-reconocido.txt"
        with open(path, encoding="utf-8") as handle:
            self.assertEqual(handle.read().strip(), "hacer algo raro")


if __name__ == "__main__":
    unittest.main()
