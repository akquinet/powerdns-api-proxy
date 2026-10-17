from functools import lru_cache
from typing import Any, TypedDict

from pydantic import BaseModel, field_validator, model_validator

from powerdns_api_proxy.exceptions import ZoneNotAllowedException
from powerdns_api_proxy.logging import logger
from powerdns_api_proxy.utils import (
    check_subzone,
    check_zone_in_regex,
    check_zones_equal,
)


class ProxyConfigServices(BaseModel):
    acme: bool = False


class ProxyConfigZone(BaseModel):
    """
    `name` is the zone name. It may be omitted when a `kind`, `account` or
    `catalog` filter is set, in which case the zone matches by attribute only.
    `description` is a description of the zone.
    `regex` should be set to `True` if `name` is a regex.
    `records` is a list of record names that are allowed.
    `regex_records` is a list of record regexes that are allowed.
    `admin` enabled creating and deleting the zone.
    `subzones` sets the same permissions on all subzones.
    `all_records` will be set to `True` if no `records` are defined.
    `cryptokeys` enables management of DNSSEC.
    `read_only` controls write permissions for this specific zone.
    `kind`, `account` and `catalog` filter zones by their PowerDNS attributes.
    """

    name: str = ""
    regex: bool = False
    description: str = ""
    records: list[str] = []
    regex_records: list[str] = []
    services: ProxyConfigServices = ProxyConfigServices(acme=False)
    admin: bool = False
    subzones: bool = False
    all_records: bool = False
    read_only: bool = False
    cryptokeys: bool = False
    kind: str = ""
    account: str = ""
    catalog: str = ""

    @model_validator(mode="after")
    def name_or_attr_filter_defined(self):
        if not self.name:
            if not (self.kind or self.account or self.catalog):
                raise ValueError(
                    "a zone requires a name or a kind/account/catalog filter"
                )
            if self.regex or self.records or self.regex_records or self.subzones:
                raise ValueError(
                    "regex, records, regex_records and subzones require a zone name"
                )
        return self

    def __init__(self, **data):
        super().__init__(**data)
        if len(self.records) == 0 and len(self.regex_records) == 0:
            logger.debug(
                f"Setting all_records to True for zone {self.name}, because no records are defined"
            )
            self.all_records = True
            self.services.acme = True

    @property
    def has_attribute_filter(self) -> bool:
        return bool(self.kind or self.account or self.catalog)

    def matches_attrs(self, pdns_zone: dict[str, Any]) -> bool:
        """Returns True if the upstream zone matches kind/account/catalog."""
        if self.kind and pdns_zone.get("kind", "").lower() != self.kind.lower():
            return False
        if self.account and (pdns_zone.get("account") or "") != self.account:
            return False
        if self.catalog and not check_zones_equal(
            pdns_zone.get("catalog") or "", self.catalog
        ):
            return False
        return True

    @model_validator(mode="after")
    def read_only_excludes_write_access(self):
        if self.read_only:
            conflicting = [
                flag
                for flag, enabled in (
                    ("admin", self.admin),
                    ("cryptokeys", self.cryptokeys),
                )
                if enabled
            ]
            if conflicting:
                raise ValueError(
                    f'zone "{self.name}" sets read_only together with '
                    f"{', '.join(conflicting)}; read_only removes all write "
                    f"access, so those flags cannot be combined"
                )
        return self


class ProxyConfigEnvironment(BaseModel):
    name: str
    token_sha512: str
    zones: list[ProxyConfigZone] = []
    global_read_only: bool = False
    global_search: bool = False
    global_cryptokeys: bool = False
    global_tsigkeys: bool = False
    global_config: bool = False
    global_statistics: bool = False
    _zones_lookup: dict[str, ProxyConfigZone] = {}
    metrics_proxy: bool = False

    @field_validator("name")
    @classmethod
    def name_defined(cls, v):
        if len(v) == 0:
            raise ValueError("name must a non-empty string")
        return v

    @field_validator("token_sha512")
    @classmethod
    def validate_token(cls, token_sha512):
        if len(token_sha512) != 128:
            raise ValueError("A SHA512 hash must be 128 digits long")
        return token_sha512

    def __init__(self, **data):
        super().__init__(**data)

        # populate zones lookup
        for zone in self.zones:
            if zone.name:
                self._zones_lookup[zone.name] = zone

    def __hash__(self):
        return hash(
            self.name
            + self.token_sha512
            + str(self.global_read_only)
            + str(self.global_search)
            + str(self.global_tsigkeys)
            + str(self.zones)
        )

    @lru_cache(maxsize=10000)
    def get_zone_candidates(
        self, zone: str
    ) -> tuple[tuple[ProxyConfigZone, ...], tuple[ProxyConfigZone, ...]]:
        """
        Returns the config entries that can govern the given zone name.

        The first tuple contains named entries in precedence order (exact name
        first, then matches in list order). The second tuple contains
        attribute-only entries, which can only be selected once the upstream
        zone attributes are known.

        Tuples are returned because this method is cached, so callers must not
        be able to mutate the cached value.
        """
        named: list[ProxyConfigZone] = []
        exact = self._zones_lookup.get(zone)
        if exact is not None:
            named.append(exact)
        for z in self.zones:
            if not z.name or z is exact:
                continue
            if (
                check_zones_equal(zone, z.name)
                or (z.subzones and check_subzone(zone, z.name))
                or (z.regex and check_zone_in_regex(zone, z.name))
            ):
                named.append(z)
        return tuple(named), tuple(z for z in self.zones if not z.name)

    def get_zone_entry(
        self, zone: str, pdns_zone: dict[str, Any] | None = None
    ) -> ProxyConfigZone | None:
        """
        Returns the config entry that governs the given zone name, or None.

        Entries that match by name take precedence; among those, the first one
        whose attributes match wins. If a named entry matched the name but not
        its attributes, attribute-only entries are not consulted, so an
        explicit entry is never overridden by a wildcard. When `pdns_zone` is
        None, attributes are unknown: only named entries can match and their
        attribute filters are ignored, which is what zone creation uses.

        `pdns_zone` is the upstream zone object, containing at least `kind`,
        `account` and `catalog` when filters are configured.
        """
        named, attr_only = self.get_zone_candidates(zone)
        if pdns_zone is None:
            return named[0] if named else None
        for entry in named:
            if entry.matches_attrs(pdns_zone):
                return entry
        if named:
            return None
        for entry in attr_only:
            if entry.matches_attrs(pdns_zone):
                return entry
        return None

    @lru_cache(maxsize=10000)
    def get_zone_if_allowed(self, zone: str) -> ProxyConfigZone:
        """
        Returns the zone config for the given zone name.

        This is a name-only lookup (exact name, subzones, regex). It ignores
        `kind`, `account` and `catalog`, so attribute-only entries never match
        here and named entries match regardless of their attributes.
        Raises ZoneNotAllowedException if the zone is not allowed
        """
        entry = self.get_zone_entry(zone)
        if entry is None:
            raise ZoneNotAllowedException()
        return entry


class ProxyConfig(BaseModel):
    """
    Configuration for the PowerDNS API Proxy.

    Args:
        pdns_api_url: The URL of the PowerDNS API.
        pdns_api_token: The token for the PowerDNS API.
        environments: A list of environments.
        pdns_api_verify_ssl: Verify SSL certificate of the PowerDNS API.
        metrics_enabled: Enable metrics.
        metrics_require_auth: Require authentication for metrics.
        api_docs_enabled: Enable API documentation.
        index_enabled: Enable default web page
        index_html: Custom html for the homepage

    """

    pdns_api_url: str
    pdns_api_token: str
    environments: list[ProxyConfigEnvironment]
    pdns_api_verify_ssl: bool = True

    metrics_enabled: bool = True
    metrics_require_auth: bool = True

    api_docs_enabled: bool = True

    index_enabled: bool = True
    index_html: str = """
    <html>
        <head>
            <title>PowerDNS API Proxy</title>
        </head>
        <body>
            <center>
            <h1>PowerDNS API Proxy</h1>
            <p><a href="/docs">Swagger Docs</a></p>
            <q>The Domain Name Server (DNS) is the Achilles heel of the Web.<br>
            The important thing is that it's managed responsibly.</q>
            <p style="margin-top: 1em; font-size: 0.9em; color: #666;">— Tim Berners-Lee</p>
            </center>
        </body>
    </html>
"""
    # Dictionary for fast token lookups
    token_env_map: dict[str, ProxyConfigEnvironment] = {}

    @field_validator("pdns_api_url")
    @classmethod
    def api_url_defined(cls, v):
        if len(v) == 0:
            raise ValueError("pdns_api_url must a non-empty string")
        return v

    @field_validator("pdns_api_token")
    @classmethod
    def api_token_defined(cls, v):
        if len(v) == 0:
            raise ValueError("pdns_api_token must a non-empty string")
        return v

    def __init__(self, **data):
        super().__init__(**data)

        # Automatically populate token_env_map during initialization
        for env in self.environments:
            self.token_env_map[env.token_sha512] = env


class ResponseAllowed(BaseModel):
    zones: list[ProxyConfigZone]


class ResponseZoneAllowed(BaseModel):
    zone: str
    allowed: bool
    config: ProxyConfigZone | None = None


class RRSETRecord(TypedDict):
    content: str
    disabled: bool


class RRSETComment(TypedDict):
    content: str
    account: str
    modified_at: int


class RRSET(TypedDict):
    name: str
    type: str
    changetype: str
    ttl: int
    records: list[RRSETRecord]
    comments: list[RRSETComment]


class RRSETRequest(TypedDict):
    rrsets: list[RRSET]
