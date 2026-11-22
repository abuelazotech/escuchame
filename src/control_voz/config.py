from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

APP_ID = "control-voz"
APP_NAME = "Escúchame"
DEFAULT_HOTKEY = "<Super><Alt>v"
DEFAULT_MODEL = str(Path.home() / ".local/share/control-voz/modelos/vosk-model-small-es-0.42")

DEFAULT_CONFIG: dict[str, Any] = {
    "model_path": DEFAULT_MODEL,
    "hotkey": DEFAULT_HOTKEY,
    "state": "off",  # off | command | dictation
    "start_off": True,
    "wake_word_enabled": True,
    "autostart": False,
    "show_notifications": True,
    "microphone_source": "",
    "dictionary": [
        "linux mint",
        "control por voz",
        "abrir terminal",
        "cerrar ventana",
    ],
    "commands": [
        {"phrase": "abrir terminal", "action": "run", "value": "gnome-terminal", "enabled": True},
        {"phrase": "cerrar terminal", "action": "close_class", "value": "gnome-terminal", "enabled": True},
        {"phrase": "abrir navegador", "action": "run", "value": "xdg-open https://", "enabled": True},
        {"phrase": "cerrar ventana", "action": "key", "value": "alt+F4", "enabled": True},
        {"phrase": "minimizar ventana", "action": "key", "value": "super+Down", "enabled": True},
        {"phrase": "maximizar ventana", "action": "key", "value": "super+Up", "enabled": True},
        {"phrase": "siguiente ventana", "action": "key", "value": "alt+Tab", "enabled": True},
        {"phrase": "modo dictado", "action": "mode", "value": "dictation", "enabled": True},
        {"phrase": "modo comando", "action": "mode", "value": "command", "enabled": True},
        {"phrase": "apagar control", "action": "mode", "value": "off", "enabled": True},
    ],
}


def config_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    return Path(base) / APP_ID


def config_path() -> Path:
    return config_dir() / "config.json"


def ensure_config() -> dict[str, Any]:
    path = config_path()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = dict(DEFAULT_CONFIG)
            merged.update(data if isinstance(data, dict) else {})
            merged["commands"] = _normalize_commands(merged.get("commands", []))
            merged["dictionary"] = _normalize_dictionary(merged.get("dictionary", []))
            return merged
        except Exception:
            pass
    cfg = dict(DEFAULT_CONFIG)
    save_config(cfg)
    return cfg


def save_config(cfg: dict[str, Any]) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(cfg, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _normalize_commands(commands: Any) -> list[dict[str, Any]]:
    result = []
    if not isinstance(commands, list):
        return list(DEFAULT_CONFIG["commands"])
    for item in commands:
        if not isinstance(item, dict):
            continue
        phrase = str(item.get("phrase", "")).strip()
        action = str(item.get("action", "run")).strip()
        value = str(item.get("value", "")).strip()
        enabled = bool(item.get("enabled", True))
        if not phrase or not value:
            continue
        if action not in {"run", "key", "close_class", "mode"}:
            continue
        result.append({"phrase": phrase, "action": action, "value": value, "enabled": enabled})
    return result or list(DEFAULT_CONFIG["commands"])


def _normalize_dictionary(words: Any) -> list[str]:
    if not isinstance(words, list):
        return list(DEFAULT_CONFIG["dictionary"])
    out = []
    seen = set()
    for w in words:
        word = str(w).strip()
        key = word.lower()
        if not word or key in seen:
            continue
        seen.add(key)
        out.append(word)
    return out or list(DEFAULT_CONFIG["dictionary"])
