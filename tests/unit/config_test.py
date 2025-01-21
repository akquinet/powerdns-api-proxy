import os
from copy import deepcopy

import pytest
from fastapi import HTTPException

from powerdns_api_proxy.config import (
    check_acme_record_allowed,
    check_pdns_search_allowed,
    check_pdns_tsigkeys_allowed,
    check_pdns_zone_admin,
    check_pdns_zone_allowed,
    check_rrset_allowed,
    check_token_defined,
    ensure_rrsets_request_allowed,
    get_environment_for_token,
    get_only_pdns_zones_allowed,
    token_defined,
)
from powerdns_api_proxy.models import (
    RRSET,
    NotAuthorizedException,
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigServices,
    ProxyConfigZone,
    RRSETRequest,
    ZoneNotAllowedException,
)

os.environ['PROXY_CONFIG_PATH'] = './config-example.yml'

dummy_proxy_zone = ProxyConfigZone(name='test.example.com.')
dummy_proxy_environment_token = 'lashflkashlfgkashglashglashgl'
dummy_proxy_environment_token_sha512 = '127aab81f4caab9c00e72f26e4c5c4b20146201a1548a787494d999febf1b9422c1711932117f38d9be9efe46f78aa72d8f6a391101bedd6e200014f6738450d'  # noqa: E501
dummy_proxy_environment_token2 = 'aslkghlskdhglkwhegklwhelghwleghwle'
dummy_proxy_environment_token2_sha512 = '1954a12ef0bf45b3a1797437509037f178af846d880115d57668a8aaa05732deedcbbd02bfa296b4f4e043b437b733fd6131933cfdc0fb50c4cf7f9f2bdaa836'  # noqa: E501

dummy_proxy_environment = ProxyConfigEnvironment(
    name='Test 1',
    zones=[dummy_proxy_zone],
    token_sha512=dummy_proxy_environment_token_sha512,
)
dummy_proxy_environment2 = ProxyConfigEnvironment(
    name='Test 2',
    zones=[dummy_proxy_zone],
    token_sha512=dummy_proxy_environment_token2_sha512,
)
dummy_proxy_config = ProxyConfig(
    pdns_api_token='blaaa',
    pdns_api_url='bluub',
    environments=[dummy_proxy_environment, dummy_proxy_environment2],
)


def test_token_not_defined_in_config_raise():
    config = dummy_proxy_config
    token = 'blablub'
    with pytest.raises(HTTPException) as err:
        check_token_defined(config, token)
    assert err.value.detail == NotAuthorizedException().detail
    assert err.value.status_code == NotAuthorizedException().status_code


def test_token_defined_in_config():
    config = dummy_proxy_config
    token = dummy_proxy_environment_token
    assert token_defined(config, token)


def test_get_only_pdns_zones_allowed():
    pdns_zones = [
        {'name': 'test1.example.com.'},
        {'name': 'test2.example.com.'},
        {'name': 'test3.example.com.'},
        {'name': 'test4.example.com.'},
    ]

    env = ProxyConfigEnvironment(
        name='Test Environment1',
        token_sha512=dummy_proxy_environment_token_sha512,
        zones=[
            ProxyConfigZone(name='test1.example.com.'),
            ProxyConfigZone(name='test3.example.com.'),
        ],
    )
    allowed = get_only_pdns_zones_allowed(env, pdns_zones)
    assert len(allowed) == len(env.zones)
    assert 'test1.example.com.' in [z.name for z in env.zones]
    assert 'test3.example.com.' in [z.name for z in env.zones]


def test_get_only_pdns_zones_allowed_glboal_read_only():
    pdns_zones = [
        {'name': 'test1.example.com.'},
        {'name': 'test2.example.com.'},
        {'name': 'test3.example.com.'},
        {'name': 'test4.example.com.'},
    ]

    env = ProxyConfigEnvironment(
        name='Test Environment1',
        token_sha512=dummy_proxy_environment_token_sha512,
        zones=[],
        global_read_only=True,
    )
    allowed = get_only_pdns_zones_allowed(env, pdns_zones)
    assert len(allowed) == len(pdns_zones)


def test_get_environment_for_token_found():
    config = dummy_proxy_config
    token = dummy_proxy_environment_token
    env = get_environment_for_token(config, token)
    assert env == dummy_proxy_environment


def test_get_environment_for_token_not_found():
    config = dummy_proxy_config
    token = 'michgibteshoffentlichnicht'
    with pytest.raises(ValueError):
        get_environment_for_token(config, token)


def test_check_pdns_zone_allowed():
    env = dummy_proxy_environment
    assert check_pdns_zone_allowed(env, dummy_proxy_zone.name)


def test_check_pdns_zone_allowed_false():
    env = dummy_proxy_environment
    assert not check_pdns_zone_allowed(env, 'blablubTest24.example.com.')


def test_check_pdns_zone_allowed_global_read_only():
    env = deepcopy(dummy_proxy_environment)
    env.global_read_only = True
    assert check_pdns_zone_allowed(env, 'blablubTest24.example.com.') is True


def test_check_pdns_zone_allowed_subzone():
    env = dummy_proxy_environment
    env.zones[0].subzones = True
    assert check_pdns_zone_allowed(env, 'blablubTest24.' + env.zones[0].name)


def test_check_pdns_zone_admin():
    env = dummy_proxy_environment
    dummy_proxy_environment.zones[0].admin = True
    assert check_pdns_zone_admin(env, dummy_proxy_zone.name)


def test_check_pdns_zone_admin_false():
    env = dummy_proxy_environment
    dummy_proxy_environment.zones[0].admin = False
    assert not check_pdns_zone_admin(env, dummy_proxy_zone.name)


def test_check_pdns_zone_admin_false_not_found():
    env = dummy_proxy_environment
    assert not check_pdns_zone_admin(env, 'blablaalball.example.com.')


def test_check_pdns_zone_admin_true_subzone():
    env = dummy_proxy_environment
    dummy_proxy_environment.zones[0].admin = True
    env.zones[0].subzones = True
    assert check_pdns_zone_admin(env, 'blablubTest24.' + env.zones[0].name)


def test_get_zone_config():
    env = dummy_proxy_environment
    zone = env.get_zone_if_allowed(dummy_proxy_zone.name)
    assert zone.name == dummy_proxy_zone.name


def test_get_zone_config_not_allowed():
    env = dummy_proxy_environment
    with pytest.raises(HTTPException) as err:
        env.get_zone_if_allowed('blablub_mich_gibtsnicht.example.com.')
    assert err.value.detail == ZoneNotAllowedException().detail
    assert err.value.status_code == ZoneNotAllowedException().status_code


def test_get_zone_config_subzone():
    env = dummy_proxy_environment
    dummy_proxy_environment.zones[0].subzones = True
    subzone = 'blabluuub.' + dummy_proxy_environment.zones[0].name
    assert env.get_zone_if_allowed(subzone)


def test_get_zone_config_subzone_subzone():
    env = dummy_proxy_environment
    dummy_proxy_environment.zones[0].subzones = True
    subzone = 'blabluuub.subzone.' + dummy_proxy_environment.zones[0].name
    assert env.get_zone_if_allowed(subzone)


def test_get_zone_config_subzone_not_allowed():
    env = dummy_proxy_environment
    subzone = 'blabluuub.' + dummy_proxy_environment.zones[0].name + 'test.'
    with pytest.raises(HTTPException) as err:
        assert env.get_zone_if_allowed(subzone)
    assert err.value.detail == ZoneNotAllowedException().detail
    assert err.value.status_code == ZoneNotAllowedException().status_code


def test_get_zone_config_no_subzone():
    env = dummy_proxy_environment
    dummy_proxy_environment.zones[0].subzones = False
    subzone = 'blabluuub.' + dummy_proxy_environment.zones[0].name
    with pytest.raises(HTTPException) as err:
        assert env.get_zone_if_allowed(subzone)
    assert err.value.detail == ZoneNotAllowedException().detail
    assert err.value.status_code == ZoneNotAllowedException().status_code


def test_check_pdns_zone_allowed_allowed_without_trailing_point():
    env = dummy_proxy_environment
    zone = dummy_proxy_zone.name[0 : len(dummy_proxy_zone.name) - 1]  # noqa: E203
    print(zone)
    assert check_pdns_zone_allowed(env, zone)


def test_check_pdns_zone_allowed_allowed_without_trailing_point_point_last_item():
    env = dummy_proxy_environment
    env.zones[0].name = 'blablub.example.com+'
    zone = 'blablub.example.com'
    assert not check_pdns_zone_allowed(env, zone)


def test_check_rrset_allowed_all_records():
    zone = ProxyConfigZone(name='test-zone.example.com.')
    for item in [
        'entry1.test-zone.example.com.',
        'entry2.entry1.test-zone.example.com',
        'test-zone.example.com.',
    ]:
        rrset: RRSET = {
            'name': item,
            'type': 'TXT',
            'changetype': 'REPLACE',
            'ttl': 3600,
            'records': [],
            'comments': [],
        }
        assert check_rrset_allowed(zone, rrset)


def test_check_rrset_allowed_single_entries():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        records=[
            'entry1.test-zone.example.com.',
            'entry2.entry1.test-zone.example.com',
            'test-zone.example.com.',
        ],
    )
    for item in [
        'entry1.test-zone.example.com.',
        'entry2.entry1.test-zone.example.com',
        'test-zone.example.com.',
    ]:
        rrset: RRSET = {
            'name': item,
            'type': 'TXT',
            'changetype': 'REPLACE',
            'ttl': 3600,
            'records': [],
            'comments': [],
        }
        assert check_rrset_allowed(zone, rrset)


def test_check_rrset_not_allowed_single_entries():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        records=[
            'entry1.test-zone.example.com.',
            'entry2.entry1.test-zone.example.com',
            'test-zone.example.com.',
        ],
    )
    for item in [
        'entry100.test-zone.example.com.',
        'entry200.entry1.test-zone.example.com',
        'test-record.example.com.',
    ]:
        rrset: RRSET = {
            'name': item,
            'type': 'TXT',
            'changetype': 'REPLACE',
            'ttl': 3600,
            'records': [],
            'comments': [],
        }
        assert not check_rrset_allowed(zone, rrset)


def test_check_rrsets_request_allowed_no_raise():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        records=[
            'entry1.test-zone.example.com.',
            'entry2.entry1.test-zone.example.com',
            'test-zone.example.com.',
        ],
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        'entry1.test-zone.example.com.',
        'entry2.entry1.test-zone.example.com',
        'test-zone.example.com.',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    assert ensure_rrsets_request_allowed(zone, request)


def test_check_rrsets_request_allowed_raise():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        records=[
            'test-zone.example.com.',
        ],
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        'entry1.test-zone.example.com.',
        'test-zone.example.com.',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    with pytest.raises(HTTPException) as err:
        ensure_rrsets_request_allowed(zone, request)
    assert err.value.status_code == 403
    assert err.value.detail == 'RRSET entry1.test-zone.example.com. not allowed'


def test_check_rrsets_request_not_allowed_read_only():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        read_only=True,
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        'entry1.test-zone.example.com.',
        'test-zone.example.com.',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    with pytest.raises(HTTPException) as err:
        ensure_rrsets_request_allowed(zone, request)
    assert err.value.status_code == 403
    assert err.value.detail == 'RRSET update not allowed with read only token'


def test_rrset_request_not_allowed_regex_empty():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        regex_records=[],
    )
    request: RRSETRequest = {'rrsets': []}
    assert ensure_rrsets_request_allowed(zone, request)


def test_rrset_request_allowed_all_regex():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        regex_records=[
            '.*',
        ],
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        'entry1.test-zone.example.com.',
        'entry2.entry1.test-zone.example.com',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    assert ensure_rrsets_request_allowed(zone, request)


def test_rrset_request_allowed_acme_regex():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        regex_records=[
            '_acme-challenge.example.*.test-zone.example.com',
        ],
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        '_acme-challenge.example-entry.test-zone.example.com.',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    assert ensure_rrsets_request_allowed(zone, request)


def test_rrset_request_not_allowed_false_regex():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        regex_records=[
            'example.*.test-zone.example.com',
        ],
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        'entry1.test-zone.example.com.',
        'entry2.entry1.test-zone.example.com',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    with pytest.raises(HTTPException) as err:
        ensure_rrsets_request_allowed(zone, request)
    assert err.value.status_code == 403
    assert err.value.detail == 'RRSET entry1.test-zone.example.com. not allowed'


def test_rrset_request_not_allowed_false_zone():
    zone = ProxyConfigZone(
        name='test-zone.example.com.',
        regex_records=[
            'example.*.test-zone2.example.com',
        ],
    )
    request: RRSETRequest = {'rrsets': []}
    for item in [
        'example1.test-zone2.example.com.',
    ]:
        request['rrsets'].append(
            {
                'name': item,
                'type': 'TXT',
                'changetype': 'REPLACE',
                'ttl': 3600,
                'records': [],
                'comments': [],
            }
        )
    with pytest.raises(HTTPException) as err:
        ensure_rrsets_request_allowed(zone, request)
    assert err.value.status_code == 403
    assert err.value.detail == 'RRSET example1.test-zone2.example.com. not allowed'


def test_check_acme_record_allowed_all_records():
    zone = ProxyConfigZone(name='test-zone.example.com', all_records=True)
    rrset = RRSET(
        name='_acme-challenge.blabub.test-zone.example.com',
        type='TXT',
        changetype='REPLACE',
        ttl=3600,
        records=[],
        comments=[],
    )
    assert check_acme_record_allowed(zone, rrset)


def test_check_acme_record_allowed_no_service_acme():
    zone = ProxyConfigZone(
        name='test-zone.example.com', records=['blabub.test-zone.example.com']
    )
    rrset = RRSET(
        name='_acme-challenge.blabub.test-zone.example.com',
        type='TXT',
        changetype='REPLACE',
        ttl=3600,
        records=[],
        comments=[],
    )
    assert not check_acme_record_allowed(zone, rrset)


def test_check_acme_record_allowed():
    zone = ProxyConfigZone(
        name='test-zone.example.com',
        records=['blabub.test-zone.example.com'],
        services=ProxyConfigServices(acme=True),
    )
    rrset = RRSET(
        name='_acme-challenge.blabub.test-zone.example.com',
        type='TXT',
        changetype='REPLACE',
        ttl=3600,
        records=[],
        comments=[],
    )
    assert check_acme_record_allowed(zone, rrset)


def test_check_acme_record_not_allowed():
    zone = ProxyConfigZone(
        name='test-zone.example.com',
        records=['hallo.test-zone.example.com'],
        services=ProxyConfigServices(acme=True),
    )
    rrset = RRSET(
        name='_acme-challenge.blabub.test-zone.example.com',
        type='TXT',
        changetype='REPLACE',
        ttl=3600,
        records=[],
        comments=[],
    )
    assert not check_acme_record_allowed(zone, rrset)


def test_check_acme_record_not_allowed_false_challenge():
    zone = ProxyConfigZone(
        name='test-zone.example.com',
        records=['blabub.test-zone.example.com'],
        services=ProxyConfigServices(acme=True),
    )
    rrset = RRSET(
        name='_acme.blabub.test-zone.example.com',
        type='TXT',
        changetype='REPLACE',
        ttl=3600,
        records=[],
        comments=[],
    )
    assert not check_acme_record_allowed(zone, rrset)


def test_search_not_allowed():
    environment = deepcopy(dummy_proxy_environment)
    environment.global_search = False
    assert check_pdns_search_allowed(environment, 'test', 'all') is False


def test_search_allowed_globally():
    environment = deepcopy(dummy_proxy_environment)
    environment.global_search = True
    assert check_pdns_search_allowed(environment, 'test', 'all') is True


def test_tsigkeys_not_allowed():
    environment = deepcopy(dummy_proxy_environment)
    environment.global_tsigkeys = False
    assert check_pdns_tsigkeys_allowed(environment) is False


def test_tsigkeys_allowed_globally():
    environment = deepcopy(dummy_proxy_environment)
    environment.global_tsigkeys = True
    assert check_pdns_tsigkeys_allowed(environment) is True
