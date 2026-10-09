"""P11 — Lightweight wake word detection.

Simple keyword matching for wake word detection.
Supports configurable wake words and sensitivity settings.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger(__name__)


@dataclass
class WakeWordResult:
    """Result of wake word detection."""
    detected: bool
    word: str = ""
    confidence: float = 0.0


class WakeWordDetector:
    """Detects wake words in audio transcript text."""

    def __init__(
        self,
        wake_words: list[str] = None,
        case_sensitive: bool = False,
        require_word_boundary: bool = True,
    ) -> None:
        self.wake_words = wake_words or ["sunny"]
        self.case_sensitive = case_sensitive
        self.require_word_boundary = require_word_boundary
        self._detection_count = 0
        self._last_detection: Optional[str] = None
        self._compiled_patterns: dict[str, re.Pattern] = {}
        self._compiled_substrings: dict[str, str] = {}

    @property
    def last_detection(self) -> Optional[str]:
        return self._last_detection

    def _get_pattern(self, word: str) -> re.Pattern:
        """Get or create a pre-compiled regex pattern for the given word."""
        if word not in self._compiled_patterns:
            self._compiled_patterns[word] = re.compile(
                rf'\b{re.escape(word)}\b'
            )
        return self._compiled_patterns[word]

    def _get_substring(self, word: str) -> str:
        """Get or create the pre-processed substring for the given word."""
        if word not in self._compiled_substrings:
            self._compiled_substrings[word] = word.lower()
        return self._compiled_substrings[word]

    def detect(self, text: str) -> WakeWordResult:
        """Check if any wake word is present in the text."""
        if not text:
            return WakeWordResult(detected=False)

        search_text = text if self.case_sensitive else text.lower()

        for word in self.wake_words:
            match_text = word if self.case_sensitive else self._get_substring(word)

            if self.require_word_boundary:
                pattern = self._get_pattern(match_text)
                if pattern.search(search_text):
                    self._detection_count += 1
                    self._last_detection = word
                    return WakeWordResult(detected=True, word=word, confidence=0.95)
            else:
                if match_text in search_text:
                    self._detection_count += 1
                    self._last_detection = word
                    return WakeWordResult(detected=True, word=word, confidence=0.8)

        return WakeWordResult(detected=False)

    def add_wake_word(self, word: str) -> None:
        if word and word not in self.wake_words:
            self.wake_words.append(word)
            if not self.case_sensitive:
                self._compiled_substrings[word] = word.lower()

    def remove_wake_word(self, word: str) -> None:
        if word in self.wake_words:
            self.wake_words.remove(word)
            self._compiled_patterns.pop(word, None)
            self._compiled_substrings.pop(word, None)

    def get_stats(self) -> dict:
        return {
            "wake_words": self.wake_words,
            "detection_count": self._detection_count,
            "last_detection": self._last_detection,
        }

    def reset(self) -> None:
        self._detection_count = 0
        self._last_detection = None
