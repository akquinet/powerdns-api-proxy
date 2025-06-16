import re


def check_subzone(zone: str, main_zone: str) -> bool:
    if zone.rstrip(".").endswith(main_zone.rstrip(".")):
        return True
    return False


def check_zone_in_regex(zone: str, regex: str) -> bool:
    """Checks if zone is in regex"""
    return re.match(regex, zone.rstrip(".")) is not None


def check_record_in_regex(record: str, regex: str) -> bool:
    """Checks if record is in regex"""
    return re.match(regex, record.rstrip(".")) is not None


def check_zones_equal(zone1: str, zone2: str) -> bool:
    """Checks if zones equal with or without trailing dot"""
    return zone1.rstrip(".") == zone2.rstrip(".")
