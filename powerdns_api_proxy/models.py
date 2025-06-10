from functools import lru_cache
from typing import TypedDict

from fastapi import HTTPException
from pydantic import BaseModel, field_validator

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
    `name` is the zone name.
    `description` is a description of the zone.
    `regex` should be set to `True` if `name` is a regex.
    `records` is a list of record names that are allowed.
    `regex_records` is a list of record regexes that are allowed.
    `admin` enabled creating and deleting the zone.
    `subzones` sets the same permissions on all subzones.
    `all_records` will be set to `True` if no `records` are defined.
    `read_only` will be set to `True` if `global_read_only` is `True`.
    """

    name: str
    regex: bool = False
    description: str = ""
    records: list[str] = []
    regex_records: list[str] = []
    services: ProxyConfigServices = ProxyConfigServices(acme=False)
    admin: bool = False
    subzones: bool = False
    all_records: bool = False
    read_only: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        if len(self.records) == 0 and len(self.regex_records) == 0:
            logger.debug(
                f"Setting all_records to True for zone {self.name}, because no records are defined"
            )
            self.all_records = True
            self.services.acme = True


class ProxyConfigEnvironment(BaseModel):
    name: str
    token_sha512: str
    zones: list[ProxyConfigZone]
    global_read_only: bool = False
    global_search: bool = False
    global_tsigkeys: bool = False
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
        if self.global_read_only:
            logger.debug(
                "Setting all subzones to read_only, because global_read_only is true"
            )
            for zone in self.zones:
                zone.read_only = True

                # populate zones lookup
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
    def get_zone_if_allowed(self, zone: str) -> ProxyConfigZone:
        """
        Returns the zone config for the given zone name
        Raises ZoneNotAllowedException if the zone is not allowed
        """
        if zone in self._zones_lookup:
            return self._zones_lookup[zone]

        for z in self.zones:
            if check_zones_equal(zone, z.name):
                return z

            if z.subzones and check_subzone(zone, z.name):
                logger.debug(f'"{zone}" is a subzone of "{z.name}"')
                return z

            if z.regex and check_zone_in_regex(zone, z.name):
                logger.debug(f'"{zone}" matches regex "{z.name}"')
                return z

        raise ZoneNotAllowedException()


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


class ZoneNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Zone not allowed"


class ZoneAdminNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Not Zone admin"


class RecordNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Record not allowed"


class RessourceNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Ressource not allowed"


class NotAuthorizedException(HTTPException):
    def __init__(self):
        self.status_code = 401
        self.detail = "Unauthorized"


class SearchNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Search not allowed"


class MetricsNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = "Metrics not allowed"


class UpstreamException(HTTPException):
    def __init__(self):
        self.status_code = 500
        self.detail = "Error while connecting to PowerDNS backend"


class UnhandledException(HTTPException):
    def __init__(self):
        self.status_code = 500
        self.detail = "Unhandled error"


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
