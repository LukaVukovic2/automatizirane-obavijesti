"""
Static file assertions for repository hygiene requirements.

Validates: Requirements 10.1, 10.2, 10.4
"""
import re
from pathlib import Path

# Project root is two levels up from this file (tests/test_smoke.py -> tests/ -> root)
PROJECT_ROOT = Path(__file__).parent.parent


class TestGitignore:
    """Requirement 10.2: .gitignore must exclude .env and previous_ids.json."""

    def setup_method(self):
        self.content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")

    def test_gitignore_excludes_dotenv(self):
        # Each line is checked so that a comment mentioning .env doesn't count
        lines = [line.strip() for line in self.content.splitlines()]
        assert ".env" in lines, ".gitignore must contain a '.env' entry"

    def test_gitignore_excludes_previous_ids_json(self):
        lines = [line.strip() for line in self.content.splitlines()]
        assert "previous_ids.json" in lines, (
            ".gitignore must contain a 'previous_ids.json' entry"
        )


class TestEnvExample:
    """Requirement 10.4: .env.example must list all required variable names."""

    REQUIRED_VARS = [
        "NJUSKALO_SEARCH_URL",
        "CHECK_INTERVAL_MINUTES",
        "DISCORD_WEBHOOK_URL",
    ]

    def setup_method(self):
        self.content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")

    def test_env_example_contains_njuskalo_search_url(self):
        assert "NJUSKALO_SEARCH_URL" in self.content, (
            ".env.example must contain NJUSKALO_SEARCH_URL"
        )

    def test_env_example_contains_check_interval_minutes(self):
        assert "CHECK_INTERVAL_MINUTES" in self.content, (
            ".env.example must contain CHECK_INTERVAL_MINUTES"
        )

    def test_env_example_contains_discord_webhook_url(self):
        assert "DISCORD_WEBHOOK_URL" in self.content, (
            ".env.example must contain DISCORD_WEBHOOK_URL"
        )

    def test_env_example_contains_all_required_vars(self):
        missing = [var for var in self.REQUIRED_VARS if var not in self.content]
        assert not missing, (
            f".env.example is missing required variable(s): {', '.join(missing)}"
        )


class TestRequirementsTxt:
    """Requirement 10.1: requirements.txt must use == pinned versions for all direct deps."""

    # Operators other than == that must NOT appear in dependency lines
    UNPINNED_OPERATORS = re.compile(r"(>=|<=|~=|!=|>(?!=)|<(?!=)|\^)")

    def _dependency_lines(self) -> list[str]:
        """Return non-blank, non-comment lines from requirements.txt."""
        content = (PROJECT_ROOT / "requirements.txt").read_text(encoding="utf-8")
        return [
            line.strip()
            for line in content.splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    def test_all_dependencies_use_pinned_versions(self):
        dep_lines = self._dependency_lines()
        assert dep_lines, "requirements.txt has no dependency lines"
        unpinned = [line for line in dep_lines if "==" not in line]
        assert not unpinned, (
            f"The following lines in requirements.txt are not pinned with ==: "
            f"{unpinned}"
        )

    def test_no_dependency_uses_range_operators(self):
        dep_lines = self._dependency_lines()
        bad_lines = [
            line for line in dep_lines if self.UNPINNED_OPERATORS.search(line)
        ]
        assert not bad_lines, (
            f"The following lines in requirements.txt use non-pinned operators: "
            f"{bad_lines}"
        )
