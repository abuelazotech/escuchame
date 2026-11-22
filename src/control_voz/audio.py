from __future__ import annotations

import shutil
import subprocess


def list_sources() -> list[tuple[str, str]]:
    if not shutil.which("pactl"):
        return []
    try:
        out = subprocess.check_output(["pactl", "list", "short", "sources"], text=True, stderr=subprocess.DEVNULL)
    except Exception:
        return []
    sources = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 2:
            name = parts[1].strip()
            if name and "monitor" not in name.lower():
                sources.append((name, name))
    return sources


def default_source() -> str:
    if not shutil.which("pactl"):
        return ""
    try:
        return subprocess.check_output(["pactl", "get-default-source"], text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""
