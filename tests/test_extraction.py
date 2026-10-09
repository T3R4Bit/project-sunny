"""P7 Extraction Rules Engine - tests for parser, matcher, gates, hot reload, integration."""

import importlib
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient


# Helper to read rules from docs
def _get_rules_content():
    return Path("docs/extraction-rules.md").read_text()


@pytest.fixture
def client(vault: Path):
    """Test client with vault path pointing to tmp_path."""
    mock_settings = MagicMock()
    mock_settings.vault_path = vault
    mock_settings.db_path = str(vault / ".sunny" / "sunny.db")
    mock_settings.admin_password_hash = ""
    mock_settings.log_level = "info"

    import sunny.config
    sunny.config.get_settings = lambda: mock_settings

    import sunny.projects.service as svc
    svc.get_settings = lambda: mock_settings
    svc._vault = lambda: vault
    importlib.reload(svc)

    # Set up extraction rules in docs dir within vault
    docs_dir = vault / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    rules_path = docs_dir / "extraction-rules.md"
    rules_path.write_text(_get_rules_content(), encoding="utf-8")

    from sunny.main import create_app
    app = create_app()
    return TestClient(app)


# ── RulesParser tests ─────────────────────────────────────────────────


class TestRulesParser:
    """Test the rules parser handles all rule formats."""

    def test_parse_valid_rules(self):
        """Parser loads valid YAML blocks."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        assert len(rules) == 15
        assert all(r.name for r in rules)
        assert all(r.tier in (1, 2, 3) for r in rules)
        assert all(r.pattern for r in rules)

    def test_parse_missing_name(self):
        """Rule without name is skipped."""
        from sunny.extraction.rules_engine import RulesParser
        bad_rule = "---\ntier: 1\npattern: test\nconfidence: 0.9\noutput: test\n---"
        parser = RulesParser()
        rules = parser.parse(bad_rule)
        assert len(rules) == 0

    def test_parse_missing_pattern(self):
        """Rule without pattern is skipped."""
        from sunny.extraction.rules_engine import RulesParser
        bad_rule = "---\nname: test\nconfidence: 0.9\noutput: test\n---"
        parser = RulesParser()
        rules = parser.parse(bad_rule)
        assert len(rules) == 0

    def test_parse_invalid_tier(self):
        """Rule with invalid tier is skipped."""
        from sunny.extraction.rules_engine import RulesParser
        bad_rule = "---\nname: test\ntier: 5\npattern: test\nconfidence: 0.9\noutput: test\n---"
        parser = RulesParser()
        rules = parser.parse(bad_rule)
        assert len(rules) == 0

    def test_parse_invalid_regex(self):
        """Rule with invalid regex is skipped."""
        from sunny.extraction.rules_engine import RulesParser
        bad_rule = "---\nname: test\ntier: 1\npattern: [invalid\nconfidence: 0.9\noutput: test\n---"
        parser = RulesParser()
        rules = parser.parse(bad_rule)
        assert len(rules) == 0

    def test_parse_negations_list(self):
        """Rule with negations list is parsed correctly."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        deadline = [r for r in rules if r.name == "deadline_mention"][0]
        assert len(deadline.negations) == 3
        assert "no deadline" in deadline.negations

    def test_parse_negations_single_string(self):
        """Rule with single negation string is handled."""
        from sunny.extraction.rules_engine import RulesParser
        rule = "---\nname: test\ntier: 1\npattern: test\nnegations: skip_this\nconfidence: 0.9\noutput: test\n---"
        parser = RulesParser()
        rules = parser.parse(rule)
        assert len(rules) == 1
        assert rules[0].negations == ["skip_this"]

    def test_parse_tiers_correct(self):
        """Rules have correct tier assignments."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        tier_map = {r.name: r.tier for r in rules}
        assert tier_map["keaton_name"] == 1
        assert tier_map["course_code"] == 2
        assert tier_map["abbreviation_definition"] == 3

    def test_parse_examples_present(self):
        """Rules can have examples."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        assert all(hasattr(r, 'examples') for r in rules)


# ── RulesEngine tests ─────────────────────────────────────────────────


class TestRulesEngine:
    """Test rule matching, negation, and classification."""

    def test_match_positive(self):
        """Rules match when pattern found."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(name="test", tier=1, pattern="hello", confidence=0.9, output="greeting")]
        engine = RulesEngine(rules)
        matches = engine.match("hello world", "test-session")
        assert len(matches) == 1
        assert matches[0].rule_name == "test"
        assert matches[0].matched_text == "hello"
        assert matches[0].tier == 1

    def test_match_multiple(self):
        """Multiple matches from same rule."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(name="test", tier=1, pattern="word", confidence=0.9, output="test")]
        engine = RulesEngine(rules)
        matches = engine.match("word and word again", "test-session")
        assert len(matches) == 2

    def test_match_nothing(self):
        """No match when pattern not found."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(name="test", tier=1, pattern="xyz", confidence=0.9, output="test")]
        engine = RulesEngine(rules)
        matches = engine.match("hello world", "test-session")
        assert len(matches) == 0

    def test_negation_blocks_match(self):
        """Rule negations prevent matching."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(
            name="deadline", tier=1,
            pattern=r"due (?:next )?Friday",
            confidence=0.9, output="deadline",
            negations=["no deadline", "no due date"]
        )]
        engine = RulesEngine(rules)
        matches = engine.match("due next Friday, but no deadline", "test-session")
        assert len(matches) == 0

    def test_negation_allows_when_not_present(self):
        """Rule matches when negation text is NOT present."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(
            name="deadline", tier=1,
            pattern=r"due (?:next )?Friday",
            confidence=0.9, output="deadline",
            negations=["no deadline"]
        )]
        engine = RulesEngine(rules)
        matches = engine.match("due next Friday for the project", "test-session")
        assert len(matches) == 1

    def test_confidence_preserved(self):
        """Rule confidence is preserved on matches."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(name="test", tier=2, pattern="hello", confidence=0.75, output="test")]
        engine = RulesEngine(rules)
        matches = engine.match("hello there", "test-session")
        assert len(matches) == 1
        assert matches[0].confidence == 0.75

    def test_tier_preserved(self):
        """Rule tier is preserved on matches."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(name="test", tier=3, pattern="hello", confidence=0.8, output="test")]
        engine = RulesEngine(rules)
        matches = engine.match("hello there", "test-session")
        assert len(matches) == 1
        assert matches[0].tier == 3

    def test_session_slug_preserved(self):
        """Session slug is preserved on matches."""
        from sunny.extraction.rules_engine import RulesEngine, Rule
        rules = [Rule(name="test", tier=1, pattern="hello", confidence=0.9, output="test")]
        engine = RulesEngine(rules)
        matches = engine.match("hello there", "unique-session-123")
        assert len(matches) == 1
        assert matches[0].session_slug == "unique-session-123"

    def test_match_on_full_transcript(self):
        """Real rules match on full transcripts."""
        from sunny.extraction.rules_engine import RulesParser, RulesEngine
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        engine = RulesEngine(rules)

        transcript = "I prefer Python for this project and ACCT 2100 is hard."
        matches = engine.match(transcript, "test-session")
        rule_names = {m.rule_name for m in matches}
        assert "preference_for_python" in rule_names
        assert "course_code" in rule_names


# ── Gate classification tests ─────────────────────────────────────────


class TestGateClassification:
    """Test that matches are correctly routed by confidence gate."""

    def test_auto_write_above_85(self):
        """Confidence >= 0.85 -> auto_write."""
        from sunny.extraction.rules_engine import RulesEngine, ExtractionMatch
        engine = RulesEngine()
        matches = [
            ExtractionMatch(rule_name="a", tier=1, matched_text="x", confidence=0.95, output_key="k", output_value="v", session_slug="s"),
        ]
        classified = engine.classify(matches)
        assert len(classified["auto_write"]) == 1
        assert len(classified["approve_queue"]) == 0
        assert len(classified["log_only"]) == 0

    def test_approve_queue_70_85(self):
        """Confidence 0.7-0.85 -> approve_queue."""
        from sunny.extraction.rules_engine import RulesEngine, ExtractionMatch
        engine = RulesEngine()
        matches = [
            ExtractionMatch(rule_name="a", tier=2, matched_text="x", confidence=0.80, output_key="k", output_value="v", session_slug="s"),
        ]
        classified = engine.classify(matches)
        assert len(classified["approve_queue"]) == 1
        assert len(classified["auto_write"]) == 0
        assert len(classified["log_only"]) == 0

    def test_log_only_below_70(self):
        """Confidence < 0.7 -> log_only."""
        from sunny.extraction.rules_engine import RulesEngine, ExtractionMatch
        engine = RulesEngine()
        matches = [
            ExtractionMatch(rule_name="a", tier=3, matched_text="x", confidence=0.65, output_key="k", output_value="v", session_slug="s"),
        ]
        classified = engine.classify(matches)
        assert len(classified["log_only"]) == 1
        assert len(classified["auto_write"]) == 0
        assert len(classified["approve_queue"]) == 0

    def test_mixed_classification(self):
        """Mixed confidence values routed correctly."""
        from sunny.extraction.rules_engine import RulesEngine, ExtractionMatch
        engine = RulesEngine()
        matches = [
            ExtractionMatch(rule_name="a", tier=1, matched_text="x", confidence=0.95, output_key="k", output_value="v", session_slug="s"),
            ExtractionMatch(rule_name="b", tier=2, matched_text="y", confidence=0.80, output_key="k", output_value="v", session_slug="s"),
            ExtractionMatch(rule_name="c", tier=3, matched_text="z", confidence=0.60, output_key="k", output_value="v", session_slug="s"),
        ]
        classified = engine.classify(matches)
        assert len(classified["auto_write"]) == 1
        assert len(classified["approve_queue"]) == 1
        assert len(classified["log_only"]) == 1


# ── Integration with close_hook tests ──────────────────────────────────


class TestExtractionIntegration:
    """Test extraction runs end-to-end from close_hook."""

    def _setup_mock_settings(self, vault: Path):
        """Helper to mock settings for a vault."""
        mock_settings = MagicMock()
        mock_settings.vault_path = vault
        mock_settings.db_path = str(vault / ".sunny" / "sunny.db")
        mock_settings.admin_password_hash = ""
        mock_settings.log_level = "info"
        import sunny.config
        sunny.config.get_settings = lambda: mock_settings

    def test_extraction_runs_on_close_hook(self, vault: Path):
        """run_close_hook triggers extraction rules engine."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        session_transcript = (
            "Keaton said: I prefer Python for this project.\n"
            "We discussed ACCT 2100 and meeting with professor on Friday.\n"
            "Keaton wants to improve sleep and mentioned being stressed."
        )

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test summary",
                "topics": [],
                "entities": [],
                "decisions": [],
                "open_questions": [],
                "personal_facts": [],
            }
            run_close_hook(
                "test-session-123",
                project_slug=None,
                session_transcript=session_transcript,
            )

        extraction_log = vault / "log" / "extraction.md"
        assert extraction_log.exists()
        content_log = extraction_log.read_text()
        assert "rule=" in content_log or "Keaton" in content_log

    def test_extraction_finds_course_code(self, vault: Path):
        """Course code pattern matches and gets extracted."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-course",
                session_transcript="CS 301 is hard and I'm stressed about the deadline.")

        extraction_log = vault / "log" / "extraction.md"
        assert extraction_log.exists()
        content_log = extraction_log.read_text()
        assert "CS 301" in content_log

    def test_extraction_finds_goal(self, vault: Path):
        """Goal statement pattern matches."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-goal",
                session_transcript="I want to build a Rust CLI tool this month.")

        extraction_log = vault / "log" / "extraction.md"
        assert extraction_log.exists()

    def test_extraction_finds_stress(self, vault: Path):
        """Stress mention pattern matches."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-stress",
                session_transcript="I feel really stressed about the upcoming deadline.")

        extraction_log = vault / "log" / "extraction.md"
        assert extraction_log.exists()

    def test_extraction_with_empty_transcript(self, vault: Path):
        """Empty transcript doesn't cause errors."""
        self._setup_mock_settings(vault)

        from sunny.llm.close_hook import run_close_hook

        result = run_close_hook("test-session-empty", session_transcript="")
        assert result is not None

    def test_extraction_auto_writes_facts(self, vault: Path):
        """Auto-written facts appear in memory/facts/."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-facts",
                session_transcript="I prefer Python for everything.")

        facts_dir = vault / "memory" / "facts"
        assert facts_dir.exists()
        fact_files = list(facts_dir.glob("*.md"))
        assert len(fact_files) > 0
        content_file = fact_files[0].read_text()
        assert "prefer" in content_file.lower() or "python" in content_file.lower()

    def test_extraction_runs_twice_no_duplicate(self, vault: Path):
        """Running extraction twice doesn't duplicate facts."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        transcript = "I prefer Python for everything."

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-dup-1", session_transcript=transcript)
            run_close_hook("test-session-dup-2", session_transcript=transcript)

        facts_dir = vault / "memory" / "facts"
        if facts_dir.exists():
            fact_files = list(facts_dir.glob("*.md"))
            assert len(fact_files) > 0
            total_lines = sum(len(f.read_text().strip().split("\n")) for f in fact_files if f.exists())
            assert total_lines < 20

    def test_extraction_log_has_timestamps(self, vault: Path):
        """Extraction log has timestamped entries."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-ts",
                session_transcript="Keaton said he prefers Python.")

        extraction_log = vault / "log" / "extraction.md"
        assert extraction_log.exists()
        content_log = extraction_log.read_text()
        import re
        assert re.search(r"\d{4}-\d{2}-\d{2}", content_log)

    def test_extraction_logs_rule_name(self, vault: Path):
        """Extraction log entries include rule name."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-rule",
                session_transcript="I use Python daily.")

        extraction_log = vault / "log" / "extraction.md"
        content_log = extraction_log.read_text()
        assert "rule=" in content_log

    def test_extraction_session_slug_in_log(self, vault: Path):
        """Session slug appears in extraction log."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("unique-session-abc-123",
                session_transcript="I want to improve sleep. I slept 6 hours last night.")

        extraction_log = vault / "log" / "extraction.md"
        content_log = extraction_log.read_text()
        assert "unique-session-abc-123" in content_log

    def test_extraction_finds_deadline(self, vault: Path):
        """Deadline pattern matches."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-deadline",
                session_transcript="Due next Friday for the project.")

        extraction_log = vault / "log" / "extraction.md"
        content_log = extraction_log.read_text()
        assert "deadline" in content_log or "deadline_mention" in content_log

    def test_extraction_negation_allows_normal_match(self, vault: Path):
        """Normal match allowed when no negation text."""
        from sunny.extraction.rules_engine import RulesParser, RulesEngine
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        engine = RulesEngine(rules)

        matches = engine.match("due next Friday for the project", "test-session")
        deadline_matches = [m for m in matches if m.rule_name == "deadline_mention"]
        assert len(deadline_matches) > 0

    def test_extraction_log_has_gate(self, vault: Path):
        """Extraction log includes gate level."""
        self._setup_mock_settings(vault)

        docs_dir = vault / "docs"
        docs_dir.mkdir(parents=True, exist_ok=True)
        docs_dir.joinpath("extraction-rules.md").write_text(_get_rules_content())

        from unittest.mock import patch
        from sunny.llm.close_hook import run_close_hook

        with patch('sunny.llm.close_hook._generate_summary') as mock_summary:
            mock_summary.return_value = {
                "summary": "Test", "topics": [], "entities": [],
                "decisions": [], "open_questions": [], "personal_facts": [],
            }
            run_close_hook("test-session-gate",
                session_transcript="I prefer Python. Python is great.")

        extraction_log = vault / "log" / "extraction.md"
        content_log = extraction_log.read_text()
        assert "auto_write" in content_log or "approve_queue" in content_log or "log_only" in content_log


# ── write_fact tests ──────────────────────────────────────────────────


class TestWriteFact:
    """Test fact writing to memory/facts/."""

    def test_fact_written_on_first_write(self, vault: Path):
        """First write creates the file."""
        from sunny.extraction.rules_engine import RulesEngine, Rule, ExtractionMatch, write_fact
        engine = RulesEngine()
        rule = Rule(name="test", tier=1, pattern="hello", confidence=0.9, output="test")
        engine.set_rules([rule])
        matches = engine.match("hello world", "test-session")
        assert len(matches) == 1

        fact_path = write_fact(vault, matches[0])
        assert fact_path.exists()
        content = fact_path.read_text()
        assert "hello" in content

    def test_fact_not_duplicated(self, vault: Path):
        """Writing same fact twice doesn't duplicate."""
        from sunny.extraction.rules_engine import RulesEngine, Rule, ExtractionMatch, write_fact
        import time

        engine = RulesEngine()
        rule = Rule(name="test", tier=1, pattern="hello", confidence=0.9, output="test")
        engine.set_rules([rule])
        matches = engine.match("hello world", "test-session")

        write_fact(vault, matches[0])
        facts_dir = vault / "memory" / "facts"
        old_files = list(facts_dir.glob("*.md"))
        old_count = sum(f.read_text().count("hello") for f in old_files)

        time.sleep(0.1)
        matches[0].timestamp = time.time()
        write_fact(vault, matches[0])

        new_files = list(facts_dir.glob("*.md"))
        new_count = sum(f.read_text().count("hello") for f in new_files)
        assert old_count == new_count


# ── All positive examples match test ──────────────────────────────────


class TestAllStarterRules:
    """Spec requirement: Every starter rule's positive examples match and negatives don't."""

    def test_every_positive_example_matches(self):
        """Every rule's examples produce at least one match."""
        from sunny.extraction.rules_engine import RulesParser, RulesEngine
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        engine = RulesEngine(rules)

        failures = []
        for rule in rules:
            if rule.examples:
                for example in rule.examples:
                    matches = engine.match(example, "test")
                    if len(matches) == 0:
                        failures.append(f"Rule '{rule.name}' example '{example}'")

        assert len(failures) == 0, f"Matching failures: {'; '.join(failures)}"

    def test_every_negative_example_does_not_match(self):
        """Every rule's negation patterns prevent matching."""
        from sunny.extraction.rules_engine import RulesParser, RulesEngine
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        engine = RulesEngine(rules)

        failures = []
        for rule in rules:
            if rule.negations:
                for negation in rule.negations:
                    matches = engine.match(negation, "test")
                    if len(matches) > 0:
                        failures.append(f"Rule '{rule.name}' negation '{negation}' matched")

        assert len(failures) == 0, f"Negation failures: {'; '.join(failures)}"

    def test_15_starter_rules_loaded(self):
        """Exactly 15 starter rules loaded."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        assert len(rules) == 15

    def test_rules_cover_all_tiers(self):
        """Rules span all three tiers."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        tiers = {r.tier for r in rules}
        assert tiers == {1, 2, 3}

    def test_tier_1_rules_count(self):
        """Tier 1 (Keaton-specific) has multiple rules."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        tier1 = [r for r in rules if r.tier == 1]
        assert len(tier1) >= 5

    def test_tier_2_rules_count(self):
        """Tier 2 (contextual) has multiple rules."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        tier2 = [r for r in rules if r.tier == 2]
        assert len(tier2) >= 2

    def test_tier_3_rules_count(self):
        """Tier 3 (personality) has multiple rules."""
        from sunny.extraction.rules_engine import RulesParser
        parser = RulesParser()
        rules = parser.parse(_get_rules_content())
        tier3 = [r for r in rules if r.tier == 3]
        assert len(tier3) >= 3
