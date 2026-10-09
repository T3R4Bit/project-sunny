"""Extraction rules engine - parses rules, matches transcripts, gates findings.

Per spec 13:
- Rules live in docs/extraction-rules.md
- Each rule: YAML block with name, tier (1|2|3), pattern (regex), negations, examples, confidence, output
- Runs on every closed session transcript
- Gates: >0.85 auto-write to memory/facts/, 0.7-0.85 queue for briefing approval, <0.7 log only
- Every decision logged to log/extraction.md
- Hot reload on file change; malformed rules skipped and reported
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

log = logging.getLogger(__name__)


@dataclass
class Rule:
    """A single extraction rule."""
    name: str
    tier: int  # 1=Keaton-specific, 2=contextual, 3=personality
    pattern: str  # regex pattern
    negations: list[str] = field(default_factory=list)
    confidence: float = 1.0
    output: str = ""  # key for structured output
    description: str = ""  # human-readable description
    examples: list[str] = field(default_factory=list)


@dataclass
class ExtractionMatch:
    """A match found by the rules engine."""
    rule_name: str
    tier: int
    matched_text: str
    confidence: float
    output_key: str
    output_value: str
    session_slug: str
    timestamp: float = field(default_factory=time.time)


class RulesParser:
    """Parse extraction rules from docs/extraction-rules.md."""

    def parse(self, content: str) -> list[Rule]:
        """Parse rules from the markdown file content. Returns list of valid rules, logs errors for malformed ones."""
        rules = []
        errors = []

        blocks = self._split_blocks(content)

        for i, block in enumerate(blocks):
            try:
                rule = self._parse_block(block, i)
                if rule:
                    rules.append(rule)
            except Exception as e:
                errors.append(f"Rule block {i}: {e}")
                log.warning("Skipping malformed extraction rule block %d: %s", i, e)

        if errors:
            log.warning("Extraction rules parse errors: %s", errors)

        return rules

    def _split_blocks(self, content: str) -> list[str]:
        """Split content into YAML blocks separated by ---."""
        blocks = []
        current_block = []
        in_block = False

        for line in content.split('\n'):
            if line.strip() == '---':
                if in_block:
                    blocks.append('\n'.join(current_block))
                    current_block = []
                    in_block = False
                else:
                    in_block = True
            elif in_block:
                current_block.append(line)

        return blocks

    def _parse_block(self, block: str, index: int) -> Optional[Rule]:
        """Parse a single YAML block into a Rule."""
        import yaml

        doc = yaml.safe_load(block)
        if not isinstance(doc, dict):
            return None

        name = doc.get('name')
        if not name:
            raise ValueError("missing 'name'")
        name = str(name)

        tier = doc.get('tier', 1)
        try:
            tier = int(tier)
            if tier not in (1, 2, 3):
                raise ValueError(f"tier must be 1, 2, or 3, got {tier}")
        except (ValueError, TypeError):
            raise ValueError(f"invalid tier: {tier}")

        pattern = doc.get('pattern')
        if not pattern:
            raise ValueError("missing 'pattern'")
        pattern = str(pattern)

        try:
            re.compile(pattern)
        except re.error as e:
            raise ValueError(f"invalid regex pattern: {e}")

        negations = doc.get('negations', [])
        if not isinstance(negations, list):
            negations = [negations]
        negations = [str(n) for n in negations if n]

        confidence = doc.get('confidence', 1.0)
        try:
            confidence = float(confidence)
        except (ValueError, TypeError):
            confidence = 1.0

        output = str(doc.get('output', name))
        description = str(doc.get('description', ''))
        examples = doc.get('examples', [])
        if not isinstance(examples, list):
            examples = [examples]
        examples = [str(e) for e in examples]

        return Rule(
            name=name,
            tier=tier,
            pattern=pattern,
            negations=negations,
            confidence=confidence,
            output=output,
            description=description,
            examples=examples,
        )


class RulesEngine:
    """Apply extraction rules to text content."""

    def __init__(self, rules: list[Rule] | None = None):
        self.rules = rules or []
        self._compiled: dict[str, re.Pattern] = {}
        # Pre-compile patterns on init
        for rule in self.rules:
            try:
                self._compiled[rule.name] = re.compile(rule.pattern, re.IGNORECASE)
            except re.error:
                log.warning("Cannot compile pattern for rule %s, skipping", rule.name)

    def set_rules(self, rules: list[Rule]) -> None:
        """Replace all rules and pre-compile patterns."""
        self.rules = rules
        self._compiled.clear()
        for rule in rules:
            try:
                self._compiled[rule.name] = re.compile(rule.pattern, re.IGNORECASE)
            except re.error:
                log.warning("Cannot compile pattern for rule %s, skipping", rule.name)

    def match(self, text: str, session_slug: str) -> list[ExtractionMatch]:
        """Run all rules against text, return matches."""
        matches = []

        for rule in self.rules:
            compiled = self._compiled.get(rule.name)
            if compiled is None:
                continue

            for neg in rule.negations:
                if re.search(neg, text, re.IGNORECASE):
                    log.debug("Rule %s negated by '%s', skipping", rule.name, neg)
                    break
            else:
                for m in compiled.finditer(text):
                    matched_text = m.group(0)
                    matches.append(ExtractionMatch(
                        rule_name=rule.name,
                        tier=rule.tier,
                        matched_text=matched_text,
                        confidence=rule.confidence,
                        output_key=rule.output,
                        output_value=matched_text,
                        session_slug=session_slug,
                    ))

        return matches

    def classify(self, matches: list[ExtractionMatch]) -> dict[str, list[ExtractionMatch]]:
        """Classify matches into gate categories."""
        auto_write = []
        approve_queue = []
        log_only = []

        for match in matches:
            if match.confidence >= 0.85:
                auto_write.append(match)
            elif match.confidence >= 0.7:
                approve_queue.append(match)
            else:
                log_only.append(match)

        return {
            'auto_write': auto_write,
            'approve_queue': approve_queue,
            'log_only': log_only,
        }


class ExtractionLog:
    """Log all extraction decisions to log/extraction.md."""

    def __init__(self, vault: Path):
        self.vault = vault
        self.log_path = vault / 'log' / 'extraction.md'

    def log_decision(self, match: ExtractionMatch, gate: str) -> None:
        """Log an extraction decision."""
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        timestamp = time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(match.timestamp))
        line = (
            f"{timestamp} | {match.session_slug} | "
            f"rule={match.rule_name} | tier={match.tier} | "
            f"confidence={match.confidence:.2f} | "
            f"gate={gate} | "
            f"text={match.matched_text[:100]}\n"
        )

        with open(self.log_path, 'a', encoding='utf-8') as f:
            f.write(line)


def write_fact(vault: Path, match: ExtractionMatch) -> Path:
    """Write an auto-written fact to memory/facts/."""
    facts_dir = vault / 'memory' / 'facts'
    facts_dir.mkdir(parents=True, exist_ok=True)

    date_str = time.strftime('%Y-%m-%d', time.gmtime(match.timestamp))
    fact_file = facts_dir / f'{date_str}.md'

    line = f"- [{match.rule_name}] {match.matched_text}\n"

    if fact_file.exists():
        content = fact_file.read_text(encoding='utf-8')
        if line.strip() in content:
            return fact_file

        with open(fact_file, 'a', encoding='utf-8') as f:
            f.write(line)
    else:
        fact_file.write_text(line, encoding='utf-8')

    return fact_file
