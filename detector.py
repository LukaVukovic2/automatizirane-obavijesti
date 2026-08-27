from parser_adapter import Listing


def detect_new(current: list[Listing], stored_ids: set[str]) -> list[Listing]:
    """
    Return listings whose listing_id is in current but not in stored_ids.
    Comparison is case-sensitive string equality.
    """
    return [listing for listing in current if listing["listing_id"] not in stored_ids]
