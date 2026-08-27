"""
Tests for detector.detect_new.

Task 9.1 — Property-based test (P4): case-sensitive ID equality
Task 9.2 — Property-based test (P7): new listing detection is exact set difference
"""

import string

import hypothesis.strategies as st
from hypothesis import assume, given, settings

from detector import detect_new
from parser_adapter import Listing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_listing(listing_id: str, **kwargs) -> Listing:
    """Create a minimal Listing dict with the given listing_id."""
    return {
        "listing_id": listing_id,
        "title": kwargs.get("title", "Test Title"),
        "price": kwargs.get("price", "100 EUR"),
        "url": kwargs.get("url", f"https://www.njuskalo.hr/oglas/{listing_id}"),
    }


# ---------------------------------------------------------------------------
# P4: Case-sensitive ID equality
# Feature: njuskalo-telegram-notifier, Property 4: case-sensitive ID equality
# ---------------------------------------------------------------------------

ALPHANUM = string.ascii_letters + string.digits
id_strategy = st.text(alphabet=ALPHANUM, min_size=1, max_size=64)


@given(listing_id=id_strategy)
@settings(max_examples=200)
def test_case_sensitive_lower_upper_are_distinct(listing_id):
    """IDs differing only in case are treated as distinct — one should not filter the other."""
    assume(listing_id != listing_id.upper())
    # Stored: the upper-case version
    stored_ids = {listing_id.upper()}
    # Current: listing with the original (lower or mixed) case ID
    current = [make_listing(listing_id)]
    # Since listing_id != listing_id.upper(), detect_new should return the listing
    result = detect_new(current, stored_ids)
    assert len(result) == 1
    assert result[0]["listing_id"] == listing_id


@given(listing_id=id_strategy)
@settings(max_examples=200)
def test_case_sensitive_upper_lower_are_distinct(listing_id):
    """Symmetric case: lower stored, upper current — still distinct."""
    assume(listing_id != listing_id.lower())
    stored_ids = {listing_id.lower()}
    current = [make_listing(listing_id)]
    result = detect_new(current, stored_ids)
    assert len(result) == 1
    assert result[0]["listing_id"] == listing_id


@given(listing_id=id_strategy)
@settings(max_examples=200)
def test_identical_id_is_filtered_out(listing_id):
    """Exact same ID in stored_ids causes the listing to be excluded from new listings."""
    stored_ids = {listing_id}
    current = [make_listing(listing_id)]
    result = detect_new(current, stored_ids)
    assert result == []


# ---------------------------------------------------------------------------
# P7: New listing detection is exact set difference
# Feature: njuskalo-telegram-notifier, Property 7: new listing detection is exact set difference
# ---------------------------------------------------------------------------

# Strategy: two lists of IDs; construct current and stored from them
id_text_strategy = st.text(alphabet=ALPHANUM, min_size=1, max_size=32)


@given(
    current_ids=st.lists(id_text_strategy, min_size=0, max_size=50, unique=True),
    stored_ids=st.frozensets(id_text_strategy, max_size=50),
)
@settings(max_examples=200)
def test_detect_new_returns_exact_set_difference(current_ids, stored_ids):
    """detect_new returns exactly current_ids - stored_ids, no additions, no omissions."""
    current = [make_listing(lid) for lid in current_ids]
    result = detect_new(current, set(stored_ids))
    result_ids = {listing["listing_id"] for listing in result}
    expected_ids = set(current_ids) - set(stored_ids)
    assert result_ids == expected_ids


@given(
    shared_ids=st.frozensets(id_text_strategy, max_size=20),
    new_ids=st.frozensets(id_text_strategy.filter(lambda x: True), min_size=1, max_size=20),
)
@settings(max_examples=200)
def test_detect_new_no_false_positives(shared_ids, new_ids):
    """detect_new never returns listings whose IDs are already in stored_ids."""
    # Make new_ids disjoint from shared_ids
    assume(not (new_ids & shared_ids))
    stored_ids = set(shared_ids)
    current_ids = list(shared_ids) + list(new_ids)
    current = [make_listing(lid) for lid in current_ids]
    result = detect_new(current, stored_ids)
    result_ids = {listing["listing_id"] for listing in result}
    # None of the stored IDs should appear in the result
    assert result_ids.isdisjoint(stored_ids)
    # All new IDs must appear in the result
    assert result_ids == set(new_ids)


@given(
    all_ids=st.lists(id_text_strategy, min_size=1, max_size=50, unique=True),
)
@settings(max_examples=200)
def test_detect_new_no_false_negatives(all_ids):
    """detect_new never omits listings whose IDs are not in stored_ids."""
    # stored_ids is empty → all current listings are new
    current = [make_listing(lid) for lid in all_ids]
    result = detect_new(current, set())
    assert result == current
