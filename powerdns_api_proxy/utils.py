import json
import re
from json.decoder import JSONDecodeError
from typing import Union

from aiohttp import ClientResponse


async def response_json_or_text(response: ClientResponse) -> Union[dict, str]:
    """Returns a `string` or a `dict` from the `ClientResponse`"""
    text = await response.text()
    try:
        return json.loads(text)
    except JSONDecodeError:
        return text


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
