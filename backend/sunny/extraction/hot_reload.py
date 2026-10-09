"""Hot reload for extraction rules — watch docs/extraction-rules.md for changes."""

from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

from sunny.extraction.rules_engine import RulesEngine, RulesParser

log = logging.getLogger(__name__)


class RulesHotReload:
    """Watch and reload extraction rules file on change."""

    def __init__(self, engine: RulesEngine, rules_path: Path):
        self.engine = engine
        self.rules_path = rules_path
        self._watcher: threading.Thread | None = None
        self._running = False
        self._last_mtime: float = 0.0
        self._lock = threading.Lock()

    def start(self) -> None:
        """Start watching for file changes in background thread."""
        if self._running:
            log.warning("Rules hot reload already running")
            return

        # Load initial rules
        self._load_rules()
        self._running = True
        self._watcher = threading.Thread(target=self._watch_loop, daemon=True)
        self._watcher.start()
        log.info("Rules hot reload started for %s", self.rules_path)

    def stop(self) -> None:
        """Stop watching."""
        self._running = False
        if self._watcher:
            self._watcher.join(timeout=5)

    def _load_rules(self) -> None:
        """Load and apply rules from the file."""
        if not self.rules_path.exists():
            log.warning("Rules file not found: %s", self.rules_path)
            return

        try:
            content = self.rules_path.read_text(encoding='utf-8')
            parser = RulesParser()
            rules = parser.parse(content)
            self.engine.set_rules(rules)
            self._last_mtime = self.rules_path.stat().st_mtime
            log.info("Loaded %d extraction rules from %s", len(rules), self.rules_path)
        except Exception as e:
            log.error("Failed to load rules from %s: %s", self.rules_path, e)

    def _watch_loop(self) -> None:
        """Background loop that checks for file changes."""
        while self._running:
            try:
                if self.rules_path.exists():
                    mtime = self.rules_path.stat().st_mtime
                    if mtime != self._last_mtime:
                        log.info("Rules file changed, reloading...")
                        self._load_rules()
            except Exception as e:
                log.warning("Error checking rules file: %s", e)

            time.sleep(2)  # Check every 2 seconds
