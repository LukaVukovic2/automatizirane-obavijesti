"""
Tests for parser_adapter._extract_listing_id.

Task 7.1 — Property-based tests (P3)
Task 7.2 — Example-based unit tests
"""

import re
import string
import sys
import os

import pytest
import hypothesis.strategies as st
from hypothesis import assume, given, settings

# Ensure the project root is on the path so parser_adapter can be imported
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from parser_adapter import _extract_listing_id

# ---------------------------------------------------------------------------
# Property 3: listing ID extraction correctness
# Feature: njuskalo-telegram-notifier, Property 3: listing ID extraction correctness
# ---------------------------------------------------------------------------

ALPHANUM = string.ascii_letters + string.digits

# Strategy for conforming IDs: alphanumeric, length 1..64
conforming_id_strategy = st.text(alphabet=ALPHANUM, min_size=1, max_size=64)


@given(listing_id=conforming_id_strategy)
@settings(max_examples=200)
def test_conforming_oglas_segment_extracted_exactly(listing_id):
    """A URL with a valid /oglas/<id> segment returns exactly that segment."""
    url = f"https://www.njuskalo.hr/nekretnine/oglas/{listing_id}"
    assert _extract_listing_id(url) == listing_id


@given(listing_id=conforming_id_strategy)
@settings(max_examples=100)
def test_conforming_oglas_with_query_string_extracted(listing_id):
    """A valid /oglas/<id> followed by ? still extracts the id."""
    url = f"https://www.njuskalo.hr/nekretnine/oglas/{listing_id}?ref=search"
    assert _extract_listing_id(url) == listing_id


@given(listing_id=conforming_id_strategy)
@settings(max_examples=100)
def test_conforming_oglas_with_fragment_extracted(listing_id):
    """A valid /oglas/<id> followed by # still extracts the id."""
    url = f"https://www.njuskalo.hr/nekretnine/oglas/{listing_id}#section"
    assert _extract_listing_id(url) == listing_id


@given(listing_id=conforming_id_strategy)
@settings(max_examples=100)
def test_conforming_oglas_with_trailing_slash_extracted(listing_id):
    """A valid /oglas/<id>/ still extracts the id."""
    url = f"https://www.njuskalo.hr/nekretnine/oglas/{listing_id}/"
    assert _extract_listing_id(url) == listing_id


@given(url=st.text())
@settings(max_examples=200)
def test_url_without_oglas_returns_none(url):
    """A URL that does not contain a conforming /oglas/<id> segment returns None."""
    assume(not re.search(r'/oglas/[A-Za-z0-9]{1,64}(?:[/?#]|$)', url))
    assert _extract_listing_id(url) is None


# ---------------------------------------------------------------------------
# Task 7.2 — Example-based unit tests
# ---------------------------------------------------------------------------

def test_valid_id_segment_is_extracted():
    """Standard Njuškalo-style URL returns the listing ID correctly."""
    url = "https://www.njuskalo.hr/prodaja-stanova/zagreb/oglas/abc123"
    assert _extract_listing_id(url) == "abc123"


def test_url_without_oglas_path_returns_none():
    """A URL with no /oglas/ path component returns None."""
    url = "https://www.njuskalo.hr/prodaja-stanova/zagreb"
    assert _extract_listing_id(url) is None


def test_id_longer_than_64_chars_returns_none():
    """A segment after /oglas/ that is longer than 64 alphanumeric chars returns None."""
    long_id = "A" * 65
    url = f"https://www.njuskalo.hr/oglas/{long_id}"
    assert _extract_listing_id(url) is None


def test_id_with_hyphen_returns_none():
    """A segment containing a hyphen (non-alphanumeric) is not extracted."""
    url = "https://www.njuskalo.hr/oglas/abc-123"
    assert _extract_listing_id(url) is None


def test_id_with_underscore_returns_none():
    """A segment containing an underscore (non-alphanumeric) is not extracted."""
    url = "https://www.njuskalo.hr/oglas/abc_123"
    assert _extract_listing_id(url) is None


def test_empty_id_segment_returns_none():
    """An empty segment after /oglas/ returns None."""
    url = "https://www.njuskalo.hr/oglas/"
    assert _extract_listing_id(url) is None


def test_single_char_id_is_extracted():
    """A single alphanumeric character is a valid ID (min length = 1)."""
    url = "https://www.njuskalo.hr/oglas/X"
    assert _extract_listing_id(url) == "X"


def test_exactly_64_char_id_is_extracted():
    """A 64-character alphanumeric ID is at the upper boundary and should be extracted."""
    id_64 = "A" * 64
    url = f"https://www.njuskalo.hr/oglas/{id_64}"
    assert _extract_listing_id(url) == id_64


def test_id_with_query_string():
    """ID followed immediately by ? is extracted correctly."""
    url = "https://www.njuskalo.hr/oglas/listing42?source=homepage"
    assert _extract_listing_id(url) == "listing42"


def test_id_with_trailing_slash():
    """ID followed immediately by / is extracted correctly."""
    url = "https://www.njuskalo.hr/oglas/listing42/"
    assert _extract_listing_id(url) == "listing42"
