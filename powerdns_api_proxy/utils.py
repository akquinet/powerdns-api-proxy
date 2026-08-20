import re


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
