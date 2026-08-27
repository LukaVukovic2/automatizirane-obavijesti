"""
conftest.py — shared test fixtures.

Prevents load_dotenv() from reading the real .env file during tests,
so tests that use patch.dict(os.environ, ..., clear=True) are fully isolated.
"""

from unittest.mock import patch

import pytest


def pytest_configure(config):
    """Register custom markers to avoid PytestUnknownMarkWarning."""
    config.addinivalue_line(
        "markers",
        "integration: marks tests as integration tests (require real config.json and .env; "
        "run with: pytest -m integration)",
    )


@pytest.fixture(autouse=True)
def _no_dotenv():
    """Suppress load_dotenv() in all tests so .env does not pollute the test env."""
    with patch("config.load_dotenv"):
        yield
