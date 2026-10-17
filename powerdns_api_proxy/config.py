import hashlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from fastapi import Depends, Header, HTTPException
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from yaml import safe_load

from powerdns_api_proxy.exceptions import (
    MetricsNotAllowedException,
    NotAuthorizedException,
    ZoneNotAllowedException,
)
from powerdns_api_proxy.logging import logger
from powerdns_api_proxy.models import (
    RRSET,
    ProxyConfig,
    ProxyConfigEnvironment,
    ProxyConfigZone,
    RRSETRequest,
)
from powerdns_api_proxy.utils import (
    check_record_in_regex,
    check_subzone,
    check_zones_equal,
)


@lru_cache(maxsize=1)
def load_config(path: Path | None = None) -> ProxyConfig:
    logger.info("Loading config")
    if not path:
        env_path = os.getenv("PROXY_CONFIG_PATH")
        if not env_path:
            raise ValueError("Could not get proxy config path")
        path = Path(env_path)
    with open(path) as f:
        data = safe_load(f)

    config = ProxyConfig(**data)

    return config


def token_defined(config: ProxyConfig, token: str) -> bool:
    sha512 = hashlib.sha512()
    sha512.update(token.encode())
    token_digest = sha512.digest().hex()

    if token_digest in config.token_env_map:
        logger.info(
            f'Authenticated environment "{config.token_env_map[token_digest].name}"'
        )
        return True
    return False


def check_token_defined(config: ProxyConfig, token: str):
    if not token_defined(config, token):
        raise NotAuthorizedException()


def dependency_check_token_defined(
    X_API_Key: str = Header(description="API Key for the proxy."),
):
    check_token_defined(load_config(), X_API_Key)


security = HTTPBasic()


def dependency_metrics_proxy_enabled(
    credentials: Annotated[HTTPBasicCredentials, Depends(security)] = Header(
        description="API Key for the proxy."
    ),
):
    username = credentials.username
    password = credentials.password

    try:
        environment = get_environment_for_token(load_config(), password)
        if not environment.name == username:
            raise NotAuthorizedException()
        if not environment.metrics_proxy:
            raise MetricsNotAllowedException()
    except ValueError:
        raise NotAuthorizedException()


def get_environment_for_token(
    config: ProxyConfig, token: str
) -> ProxyConfigEnvironment:
    """
    Returns:
        ProxyConfigEnvironment: The environment for the given token.
    Raises:
        ValueError: If no environment is found for the given token.
    """
    sha512 = hashlib.sha512()
    sha512.update(token.encode())
    token_digest = sha512.digest().hex()

    if token_digest in config.token_env_map:
        return config.token_env_map[token_digest]

    raise ValueError("Could not find a environment for the given token")


def get_only_pdns_zones_allowed(
    environment: ProxyConfigEnvironment, pdns_zones: list[dict]
) -> list[dict]:
    filtered = []
    if environment.global_read_only:
        return pdns_zones

    for zone in pdns_zones:
        named, attr_only = environment.get_zone_candidates(zone["name"])
        if not named and not attr_only:
            continue
        if select_matching_zone_entry(named, attr_only, zone) is not None:
            filtered.append(zone)
    return filtered


def check_pdns_zone_attrs_allowed(
    zone: ProxyConfigZone, pdns_zone: dict[str, Any]
) -> bool:
    """Returns True if the upstream zone matches the configured kind/account/catalog"""
    if zone.kind and pdns_zone.get("kind", "").lower() != zone.kind.lower():
        return False
    if zone.account and pdns_zone.get("account", "") != zone.account:
        return False
    if zone.catalog and pdns_zone.get("catalog", "") != zone.catalog:
        return False
    return True


def select_matching_zone_entry(
    named: list[ProxyConfigZone],
    attr_only: list[ProxyConfigZone],
    pdns_zone: dict[str, Any],
) -> ProxyConfigZone | None:
    """Returns the first entry whose attributes match, or None if none does.

    Named entries that match the zone name take precedence. If at least one
    such entry exists, the zone is denied when none of them matches its
    attributes; attribute-only entries are not consulted afterwards, because an
    explicit entry must not be overridden by a wildcard.
    """
    for zone in named:
        if check_pdns_zone_attrs_allowed(zone, pdns_zone):
            return zone
    if named:
        return None
    for zone in attr_only:
        if check_pdns_zone_attrs_allowed(zone, pdns_zone):
            return zone
    return None


def check_pdns_zone_allowed(environment: ProxyConfigEnvironment, zone: str) -> bool:
    """Returns True if zone is allowed in the environment"""
    if environment.global_read_only:
        return True

    try:
        _ = environment.get_zone_if_allowed(zone)
        return True
    except ZoneNotAllowedException:
        return False
    except Exception:
        return False


def check_pdns_zone_admin(environment: ProxyConfigEnvironment, zone: str) -> bool:
    try:
        env_zone = environment.get_zone_if_allowed(zone)
        return env_zone.admin
    except ZoneNotAllowedException:
        pass
    except Exception:
        pass
    return False


def check_pdns_zone_writable(environment: ProxyConfigEnvironment, zone: str) -> bool:
    """Returns True if writes to the zone are allowed in the environment"""
    try:
        env_zone = environment.get_zone_if_allowed(zone)
    except ZoneNotAllowedException:
        return False
    return not env_zone.read_only


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

    if (
        not zone.regex
        and not check_zones_equal(rrset["name"], zone.name)
        and not check_subzone(rrset["name"], zone.name)
    ):
        logger.debug("RRSET not allowed, because zone does not match")
        return False

    for record in zone.records:
        if check_zones_equal(rrset["name"], record):
            return True

    for regex in zone.regex_records:
        if check_record_in_regex(rrset["name"], regex):
            return True

    if check_acme_record_allowed(zone, rrset):
        return True

    return False


def check_acme_record_allowed(zone: ProxyConfigZone, rrset: RRSET) -> bool:
    if zone.all_records:
        logger.debug("ACME challenge allowed, because all records are allowed")
        return True

    if not zone.services.acme:
        logger.info("Service ACME is not activated")
        return False

    for record in zone.records:
        if check_zones_equal(f"_acme-challenge.{record}", rrset["name"]):
            logger.info(f"ACME challenge for record {record} is allowed")
            return True

    return False


def check_pdns_cryptokeys_allowed(
    environment: ProxyConfigEnvironment, zone: str
) -> bool:
    if environment.global_cryptokeys:
        return True

    try:
        return environment.get_zone_if_allowed(zone).cryptokeys
    except ZoneNotAllowedException:
        pass

    return False


def check_pdns_tsigkeys_allowed(environment: ProxyConfigEnvironment) -> bool:
    if environment.global_tsigkeys:
        return True
    return False


def check_pdns_config_allowed(environment: ProxyConfigEnvironment) -> bool:
    return environment.global_config


def check_pdns_statistics_allowed(environment: ProxyConfigEnvironment) -> bool:
    return environment.global_statistics


def ensure_rrsets_request_allowed(zone: ProxyConfigZone, request: RRSETRequest) -> bool:
    """Raises HTTPException if RRSET is not allowed"""
    if zone.read_only:
        logger.info("RRSET update not allowed with read only token")
        raise HTTPException(403, "RRSET update not allowed with read only token")
    for rrset in request["rrsets"]:
        if not check_rrset_allowed(zone, rrset):
            logger.info(f"RRSET {rrset['name']} not allowed in zone {zone.name}")
            raise HTTPException(403, f"RRSET {rrset['name']} not allowed")
        logger.info(f"RRSET {rrset['name']} allowed")
    return True
