import re

SENSITIVE_PATH_SEGMENTS = {"cryptokeys", "tsigkeys"}


def is_sensitive_path(path: str) -> bool:
    """Checks if path points at a cryptokey or tsigkey endpoint.

    Matches on path segments rather than substrings, so a zone named
    e.g. "tsigkeys.example.com" is not mistaken for the /tsigkeys endpoint.
    """
    return any(segment in SENSITIVE_PATH_SEGMENTS for segment in path.split("/"))


def check_subzone(zone: str, main_zone: str) -> bool:
    """Checks if `zone` is a subzone of `main_zone` (or equal to it)."""
    zone = zone.rstrip(".")
    main_zone = main_zone.rstrip(".")
    return zone == main_zone or zone.endswith("." + main_zone)


def check_zone_in_regex(zone: str, regex: str) -> bool:
    """Checks if zone fully matches regex"""
    return re.fullmatch(regex, zone.rstrip(".")) is not None


def check_record_in_regex(record: str, regex: str) -> bool:
    """Checks if record fully matches regex"""
    return re.fullmatch(regex, record.rstrip(".")) is not None


def check_zones_equal(zone1: str, zone2: str) -> bool:
    """Checks if zones equal with or without trailing dot"""
    return zone1.rstrip(".") == zone2.rstrip(".")
