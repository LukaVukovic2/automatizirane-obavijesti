"""
conftest.py — shared test fixtures.

Prevents load_dotenv() from reading the real .env file during tests,
so tests that use patch.dict(os.environ, ..., clear=True) are fully isolated.
"""

from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _no_dotenv():
    """Suppress load_dotenv() in all tests so .env does not pollute the test env."""
    with patch("config.load_dotenv"):
        yield
