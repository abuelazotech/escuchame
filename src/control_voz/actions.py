from __future__ import annotations

import shlex
import shutil
import subprocess
from dataclasses import dataclass


@dataclass
class Command:
    phrase: str
    action: str
    value: str
    enabled: bool = True


def run_command(cmd: Command) -> str:
    if not cmd.enabled:
        return "disabled"
    if cmd.action == "run":
        _run_shell(cmd.value)
        return "ok"
    if cmd.action == "key":
        _send_key(cmd.value)
        return "ok"
    if cmd.action == "close_class":
        _close_window_class(cmd.value)
        return "ok"
    if cmd.action == "mode":
        return cmd.value
    return "unknown"


def _run_shell(value: str) -> None:
    subprocess.Popen(value, shell=True, start_new_session=True)


def _send_key(value: str) -> None:
    if not shutil.which("xdotool"):
        return
    keys = [k.strip() for k in value.replace("+", " ").split() if k.strip()]
    if keys:
        subprocess.Popen(["xdotool", "key", "--clearmodifiers", "+".join(keys)])


def _close_window_class(window_class: str) -> None:
    if not shutil.which("xdotool"):
        return
    try:
        out = subprocess.check_output(
            ["xdotool", "search", "--class", window_class], text=True, stderr=subprocess.DEVNULL
        )
        ids = [line.strip() for line in out.splitlines() if line.strip()]
        if ids:
            subprocess.Popen(["xdotool", "windowclose", ids[-1]])
    except Exception:
        return
