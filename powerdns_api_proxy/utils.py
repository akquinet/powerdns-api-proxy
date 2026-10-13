import re

# Path parameters are forwarded into the upstream URL by string formatting, so
# only characters that the HTTP client cannot reinterpret may be passed on.
# Anything outside this allowlist would be reinterpreted as a query, fragment,
# path separator or percent-escape, and the request would hit a different
# resource than the one the permission check was made for.
#
# Besides the raw characters PowerDNS allows in zone/key names, PowerDNS encodes
# any other byte of a zone id as "=XX" (uppercase hex, see apiZoneIdToName /
# apiNameToId in ws-api.cc), so those escapes have to be accepted as well. The
# \w is unicode-aware, so IDN names (utf-8 or punycode) and wildcard zones pass.
SAFE_PATH_PARAM_PATTERN = re.compile(r"(?:[\w.*-]|=[0-9A-F]{2})+\Z")


def check_path_param_safe(value: str) -> bool:
    """Checks that a path parameter can be forwarded to PowerDNS as is."""
    if value in ("", ".", ".."):
        return False
    return SAFE_PATH_PARAM_PATTERN.fullmatch(value) is not None


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
