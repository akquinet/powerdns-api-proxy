import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Optional

from fastapi import Header, HTTPException
from yaml import safe_load

from powerdns_api_proxy.logging import logger
from powerdns_api_proxy.models import (
    RRSET,
    NotAuthorizedException,
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigZone,
    RRSETRequest,
    ZoneNotAllowedException,
)
from powerdns_api_proxy.utils import check_zones_equal


@lru_cache(maxsize=1)
def load_config(path: Optional[Path] = None) -> ProxyConfig:
    logger.info('Loading config')
    if not path:
        env_path = os.getenv('PROXY_CONFIG_PATH')
        if not env_path:
            raise ValueError('Could not get proxy config path')
        path = Path(env_path)
    with open(path) as f:
        data = safe_load(f)

    config = ProxyConfig.model_validate(data)
    return config


def token_defined(config: ProxyConfig, token: str) -> bool:
    sha512 = hashlib.sha512()
    sha512.update(token.encode())
    token_digest = sha512.digest().hex()
    for env in config.environments:
        if token_digest == env.token_sha512:
            logger.info(f'Authenticated environment "{env.name}"')
            return True
    return False


def check_token_defined(config: ProxyConfig, token: str):
    if not token_defined(config, token):
        raise NotAuthorizedException()


def dependency_check_token_defined(
    X_API_Key: str = Header(description='API Key for the proxy.'),
):
    check_token_defined(load_config(), X_API_Key)


def get_environment_for_token(
    config: ProxyConfig, token: str
) -> ProxyConfigEnvironment:
    '''
    Returns:
        ProxyConfigEnvironment: The environment for the given token.
    Raises:
        ValueError: If no environment is found for the given token.
    '''
    sha512 = hashlib.sha512()
    sha512.update(token.encode())
    token_digest = sha512.digest().hex()
    for env in config.environments:
        if token_digest == env.token_sha512:
            return env
    raise ValueError('Could not find a environment for the given token')


def get_only_pdns_zones_allowed(
    environment: ProxyConfigEnvironment, pdns_zones: list[dict]
) -> list[dict]:
    filtered = []
    if environment.global_read_only:
        return pdns_zones

    for zone in pdns_zones:
        if check_pdns_zone_allowed(environment, zone['name']):
            filtered.append(zone)
    return filtered


def check_pdns_zone_allowed(environment: ProxyConfigEnvironment, zone: str) -> bool:
    '''Returns True if zone is allowed in the environment'''
    if environment.global_read_only:
        return True

    try:
        _ = environment.get_zone_if_allowed(zone)
        return True
    except ZoneNotAllowedException:
        return False


def check_pdns_zone_admin(environment: ProxyConfigEnvironment, zone: str) -> bool:
    try:
        env_zone = environment.get_zone_if_allowed(zone)
        return env_zone.admin
    except ZoneNotAllowedException:
        pass
    return False


def check_pdns_search_allowed(
    environment: ProxyConfigEnvironment, query: str, object_type: str
) -> bool:
    if environment.global_search:
        return True
    return False


def check_rrset_allowed(zone: ProxyConfigZone, rrset: RRSET) -> bool:
    if zone.read_only:
        return False

    if zone.all_records:
        return True

    for record in zone.records:
        if check_zones_equal(rrset['name'], record):
            return True

    if check_acme_record_allowed(zone, rrset):
        return True

    return False


def check_acme_record_allowed(zone: ProxyConfigZone, rrset: RRSET) -> bool:
    if zone.all_records:
        logger.debug('ACME challenge allowed, because all records are allowed')
        return True

    if not zone.services.acme:
        logger.info('Service ACME is not activated')
        return False

    for record in zone.records:
        if check_zones_equal(f'_acme-challenge.{record}', rrset['name']):
            logger.info(f'ACME challenge for record {record} is allowed')
            return True

    return False


def ensure_rrsets_request_allowed(zone: ProxyConfigZone, request: RRSETRequest) -> bool:
    '''Raises HTTPException if RRSET is not allowed'''
    if zone.read_only:
        logger.info('RRSET update not allowed with read only token')
        raise HTTPException(403, 'RRSET update not allowed with read only token')
    for rrset in request['rrsets']:
        if not check_rrset_allowed(zone, rrset):
            logger.info(f'RRSET {rrset["name"]} not allowed in zone {zone.name}')
            raise HTTPException(403, f'RRSET {rrset["name"]} not allowed')
        logger.info(f'RRSET {rrset["name"]} allowed')
    return True


# def get_zone_config(environment: ProxyConfigEnvironment, zone: str) -> ProxyConfigZone:
#     if not check_pdns_zone_allowed:
#         raise ZoneNotAllowedException()
#     for z in environment.zones:
#         if check_zones_equal(z.name, zone):
#             return z
#         elif z.subzones:
#             if check_subzone(zone, z.name):
#                 return ProxyConfigZone(
#                     name=zone,
#                     subzones=z.subzones,
#                     services=z.services,
#                     admin=z.admin,
#                     all_records=z.all_records,
#                     records=z.records,
#                     read_only=z.read_only,
#                 )
#     raise ZoneNotAllowedException()
