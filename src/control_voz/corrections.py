from __future__ import annotations

import re
import unicodedata
from pathlib import Path

from .config import config_dir

CORRECTIONS_FILE = "correcciones.txt"
UNKNOWN_FILE = "no-reconocido.txt"
SEPARATOR = "=>"


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKD", str(text).lower())
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def corrections_path() -> Path:
    return config_dir() / CORRECTIONS_FILE


def load_corrections() -> dict[str, str]:
    corrections: dict[str, str] = {}
    try:
        lines = corrections_path().read_text(encoding="utf-8").splitlines()
    except OSError:
        return corrections
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#") or SEPARATOR not in line:
            continue
        wrong, right = (part.strip() for part in line.split(SEPARATOR, 1))
        key = normalize_text(wrong)
        value = normalize_text(right)
        if key and value and key != value:
            corrections[key] = right
    return corrections


def save_corrections(corrections: dict[str, str]) -> None:
    path = corrections_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    lines = []
    for key in sorted(corrections):
        value = corrections[key]
        value_key = normalize_text(value)
        if value_key and value_key != key:
            lines.append(f"{key} {SEPARATOR} {value}\n")
    tmp.write_text("".join(lines), encoding="utf-8")
    tmp.replace(path)


def add_correction(wrong: str, right: str) -> dict[str, str]:
    key = normalize_text(wrong)
    value = normalize_text(right)
    if not key or not value or key == value:
        return load_corrections()
    corrections = load_corrections()
    corrections[key] = right.strip()
    save_corrections(corrections)
    return corrections


def parse_correction(text: str) -> tuple[str, str] | None:
    key = normalize_text(text)
    match = re.match(r"^(?:corregir|corrige)\s+(.+)$", key)
    if not match:
        return None
    body = match.group(1).strip()
    separator = re.match(r"^(.+)\s+(?:es|con|por)\s+(.+)$", body)
    if separator:
        wrong, right = separator.group(1).strip(), separator.group(2).strip()
    else:
        parts = body.split(None, 1)
        if len(parts) != 2:
            return None
        wrong, right = parts[0].strip(), parts[1].strip()
    if not wrong or not right or wrong == right:
        return None
    return wrong, right


def _keys_sorted(corrections: dict[str, str]) -> list[str]:
    return sorted(corrections, key=lambda key: (-len(key.split()), -len(key)))


def _apply_token_matches(text: str, tokens: list[re.Match[str]], folded: list[str], values: dict[str, str]) -> str:
    keys = _keys_sorted(values)
    parts: list[str] = []
    cursor = 0
    index = 0
    while index < len(tokens):
        hit = None
        for key in keys:
            words = key.split()
            if folded[index:index + len(words)] == words:
                hit = (key, len(words))
                break
        if hit:
            key, count = hit
            parts.append(text[cursor:tokens[index].start()])
            parts.append(values[key])
            cursor = tokens[index + count - 1].end()
            index += count
            continue
        index += 1
    parts.append(text[cursor:])
    return "".join(parts)


def _valid_values(corrections: dict[str, str], normalized: bool) -> dict[str, str]:
    values = {}
    for key, value in corrections.items():
        value_key = normalize_text(value)
        if value_key and value_key != key:
            values[key] = value_key if normalized else value
    return values


def apply_corrections(text: str, corrections: dict[str, str]) -> str:
    tokens = list(re.finditer(r"[^\W_]+", text, flags=re.UNICODE))
    if not tokens:
        return text
    folded = [normalize_text(match.group(0)) for match in tokens]
    return _apply_token_matches(text, tokens, folded, _valid_values(corrections, True))


def apply_corrections_to_text(text: str, corrections: dict[str, str]) -> str:
    tokens = list(re.finditer(r"[^\W_]+", text, flags=re.UNICODE))
    if not tokens:
        return text
    folded = [normalize_text(match.group(0)) for match in tokens]
    return _apply_token_matches(text, tokens, folded, _valid_values(corrections, False))


def log_unknown(text: str) -> None:
    line = text.strip()
    if not line:
        return
    path = config_dir() / UNKNOWN_FILE
    try:
        prior = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    except OSError:
        prior = []
    if line in prior:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass
