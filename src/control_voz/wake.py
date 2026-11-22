from __future__ import annotations

from difflib import SequenceMatcher

from .corrections import normalize_text

WAKE = "wake"
SLEEP = "sleep"

_PHRASES = {
    WAKE: ("escuchame", "escucha me"),
    SLEEP: ("ensordece", "en sordece"),
}
_THRESHOLD = 0.95


def _similar(a: str, b: str) -> float:
    if abs(len(a) - len(b)) > 1:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def detect_wake(text: str) -> str | None:
    tokens = [token for token in normalize_text(text).split() if token]
    if not tokens:
        return None
    for kind, phrases in _PHRASES.items():
        for phrase in phrases:
            words = phrase.split()
            if len(words) > len(tokens):
                continue
            for index in range(len(tokens) - len(words) + 1):
                window = tokens[index:index + len(words)]
                if all(_similar(a, b) >= _THRESHOLD for a, b in zip(window, words)):
                    return kind
    return None
