from __future__ import annotations

import json
import queue
import re
import subprocess
import threading
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Callable

from .actions import Command, run_command


def _normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


@dataclass
class EngineEvent:
    kind: str
    text: str = ""


class VoiceEngine:
    def __init__(self, config: dict, on_event: Callable[[EngineEvent], None]):
        self.config = config
        self.on_event = on_event
        self.state = config.get("state", "off")
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()

    def start(self) -> None:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        proc = self._proc
        if proc:
            try:
                proc.terminate()
            except Exception:
                pass
        thread = self._thread
        if thread and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=10)
        self._thread = None
        self._proc = None

    def set_state(self, state: str) -> None:
        if state not in {"off", "command", "dictation"}:
            return
        self.state = state
        self.on_event(EngineEvent("state", state))

    def _run(self) -> None:
        try:
            from vosk import KaldiRecognizer, Model, SetLogLevel  # type: ignore
        except Exception as e:
            self.on_event(EngineEvent("error", f"Vosk no disponible: {e}"))
            return

        model_path = self.config.get("model_path", "")
        try:
            SetLogLevel(-1)
            model = Model(model_path)
        except Exception as e:
            self.on_event(EngineEvent("error", f"No se pudo cargar el modelo Vosk. Configura la ruta en Configuración. Detalle: {e}"))
            return

        commands = [Command(**c) for c in self.config.get("commands", []) if c.get("enabled", True)]
        phrases = [c.phrase for c in commands]
        phrases.extend(["modo comando", "modo dictado", "apagar control", "activar control", "activar dictado"])
        phrases.extend(self.config.get("dictionary", []))
        phrases = sorted({p for p in phrases if p})

        grammar = json.dumps(phrases, ensure_ascii=False)
        rec_cmd = KaldiRecognizer(model, 16000, grammar)
        rec_dict = KaldiRecognizer(model, 16000)

        source = self.config.get("microphone_source") or _default_source()
        cmd = [
            "parec",
            "--raw",
            "--format=s16le",
            "--rate=16000",
            "--channels=1",
        ]
        if source:
            cmd.insert(1, f"--device={source}")

        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        except Exception as e:
            self.on_event(EngineEvent("error", f"No se pudo iniciar audio: {e}"))
            return

        self.on_event(EngineEvent("state", self.state))
        assert self._proc.stdout is not None
        while not self._stop.is_set():
            data = self._proc.stdout.read(4000)
            if not data:
                break
            if self.state == "off":
                continue
            if self.state == "command":
                if rec_cmd.AcceptWaveform(data):
                    text = json.loads(rec_cmd.Result()).get("text", "").strip()
                    if text:
                        self._handle_command(text, commands)
                rec_dict.Reset()
            elif self.state == "dictation":
                # control phrases still recognized
                if rec_cmd.AcceptWaveform(data):
                    text = json.loads(rec_cmd.Result()).get("text", "").strip()
                    if text and self._handle_mode_phrase(text):
                        rec_dict.Reset()
                        continue
                    if text and self._handle_command(text, commands):
                        rec_dict.Reset()
                        continue
                if rec_dict.AcceptWaveform(data):
                    text = json.loads(rec_dict.Result()).get("text", "").strip()
                    if text:
                        self._type_text(text + " ")
                # if no final dictation, ignore partials

        try:
            if self._proc:
                self._proc.terminate()
        except Exception:
            pass
        self._proc = None

    def _handle_mode_phrase(self, text: str) -> bool:
        mapping = {
            "modo comando": "command",
            "activar control": "command",
            "modo dictado": "dictation",
            "activar dictado": "dictation",
            "apagar control": "off",
        }
        key = _normalize_text(text)
        for phrase, state in mapping.items():
            if key == _normalize_text(phrase):
                self.set_state(state)
                return True
        return False

    def _handle_command(self, text: str, commands: list[Command]) -> bool:
        if self._handle_mode_phrase(text):
            return True
        target = _normalize_text(text)
        scored = sorted(
            ((_similarity(_normalize_text(cmd.phrase), target), cmd) for cmd in commands),
            key=lambda item: item[0],
            reverse=True,
        )
        if not scored:
            return False
        score, best = scored[0]
        runner_up = scored[1][0] if len(scored) > 1 else 0.0
        if score >= 0.78 and score - runner_up >= 0.08:
            result = run_command(best)
            if best.action == "mode" and result in {"off", "command", "dictation"}:
                self.set_state(result)
            self.on_event(EngineEvent("command", text))
            return True
        self._log_unknown(text)
        return False

    @staticmethod
    def _log_unknown(text: str) -> None:
        try:
            from .config import config_dir
            (config_dir() / "no-reconocido.txt").write_text(text.strip() + "\n", encoding="utf-8")
        except Exception:
            pass

    def _type_text(self, text: str) -> None:
        try:
            subprocess.Popen(["xdotool", "type", "--clearmodifiers", "--delay", "1", text])
            self.on_event(EngineEvent("dictation", text.strip()))
        except Exception:
            pass


def _default_source() -> str:
    try:
        return subprocess.check_output(["pactl", "get-default-source"], text=True).strip()
    except Exception:
        return ""
