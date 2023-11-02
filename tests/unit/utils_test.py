import pytest
import yaml

from powerdns_api_proxy.utils import (
    check_subzone,
    check_zone_in_regex,
    check_zones_equal,
)
from tests.fixtures import FIXTURES_DIR


def test_check_subzone_true():
    zone = 'myzone.main.example.com'
    main = 'main.example.com.'
    assert check_subzone(zone, main)


def test_check_subzone_false():
    zone = 'myzone.test.example.com'
    main = 'main.example.com.'
    assert not check_subzone(zone, main)


def test_zones_equal_true():
    zone1 = 'myzone.main.example.com'
    zone2 = 'myzone.main.example.com.'
    assert check_zones_equal(zone1, zone2)


@pytest.mark.parametrize(
    'zone, regex',
    [
        ('prod.customer.example.com', '.*customer.example.com'),
        ('prod.customer.example.com', '.*\\.customer.example.com'),
        ('dns.prod.customer.example.com.', '.*customer.example.com'),
        ('prod.customer.example.com.', r'\w+\.customer.example.com'),
        ('customer.example.com.', r'\w*customer.example.com'),
        ('prod.customer.example.com.', r'\w+\.\w+\.example.com'),
    ],
)
def test_zones_in_regex_true(zone, regex):
    assert check_zone_in_regex(zone, regex)


@pytest.mark.parametrize(
    'zone, regex',
    [
        ('main.example.com.', r'\w+\.main.example.com'),  # only subzone allowed
        ('main.example.com.', r'\w+\.main.test.com'),  # false base domain
        (
            'subzone.zone.main.example.com.',
            r'\w+\.main.example.com',
        ),  # missing dot for subzone
        ('customer.example.com.', r'main.example.com'),  # only dots
    ],
)
def test_zones_in_regex_false(zone, regex):
    assert not check_zone_in_regex(zone, regex)


def test_regex_with_parsed_yaml():
    with open(FIXTURES_DIR + '/test_regex_parsing.yaml') as f:
        parsed = yaml.safe_load(f)
    regex_string = parsed['name']
    assert check_zone_in_regex('customer.example.com.', regex_string)
