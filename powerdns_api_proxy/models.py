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
    '''
    `name` is the zone name.
    `regex` should be set to `True` if `name` is a regex.
    `admin` enabled creating and deleting the zone.
    `subzones` sets the same permissions on all subzones.
    `all_records` will be set to `True` if no `records` are defined.
    `read_only` will be set to `True` if `global_read_only` is `True`.
    '''

    name: str
    regex: bool = False
    description: str = ''
    records: list[str] = []
    services: ProxyConfigServices = ProxyConfigServices(acme=False)
    admin: bool = False
    subzones: bool = False
    all_records: bool = False
    read_only: bool = False

    def __init__(self, **data):
        super().__init__(**data)
        if len(self.records) == 0:
            logger.debug(
                f'Setting all_records to True for zone {self.name}, because no records are defined'
            )
            self.all_records = True
            self.services.acme = True


class ProxyConfigEnvironment(BaseModel):
    name: str
    token_sha512: str
    zones: list[ProxyConfigZone]
    global_read_only: bool = False
    global_search: bool = False
    _zones_lookup: dict[str, ProxyConfigZone] = {}

    @field_validator('name')
    @classmethod
    def name_defined(cls, v):
        if len(v) == 0:
            raise ValueError('name must a non-empty string')
        return v

    @field_validator('token_sha512')
    @classmethod
    def validate_token(cls, token_sha512):
        if len(token_sha512) != 128:
            raise ValueError('A SHA512 hash must be 128 digits long')
        return token_sha512

    def __init__(self, **data):
        super().__init__(**data)
        if self.global_read_only:
            logger.debug(
                'Setting all subzones to read_only, because global_read_only is true'
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
            + str(self.zones)
        )

    @lru_cache(maxsize=10000)
    def get_zone_if_allowed(self, zone: str) -> ProxyConfigZone:
        '''
        Returns the zone config for the given zone name
        Raises ZoneNotAllowedException if the zone is not allowed
        '''
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
    pdns_api_url: str
    pdns_api_token: str
    environments: list[ProxyConfigEnvironment]
    pdns_api_verify_ssl: bool = True

    @field_validator('pdns_api_url')
    @classmethod
    def api_url_defined(cls, v):
        if len(v) == 0:
            raise ValueError('pdns_api_url must a non-empty string')
        return v

    @field_validator('pdns_api_token')
    @classmethod
    def api_token_defined(cls, v):
        if len(v) == 0:
            raise ValueError('pdns_api_token must a non-empty string')
        return v

    def __hash__(self):
        return hash(
            self.pdns_api_url
            + self.pdns_api_token
            + str(self.pdns_api_verify_ssl)
            + str(self.environments)
        )


class ResponseAllowed(BaseModel):
    zones: list[ProxyConfigZone]


class ResponseZoneAllowed(BaseModel):
    zone: str
    allowed: bool
    config: ProxyConfigZone | None = None


class ZoneNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = 'Zone not allowed'


class ZoneAdminNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = 'Not Zone admin'


class RecordNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = 'Record not allowed'


class RessourceNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = 'Ressource not allowed'


class NotAuthorizedException(HTTPException):
    def __init__(self):
        self.status_code = 401
        self.detail = 'Not authorized'


class SearchNotAllowedException(HTTPException):
    def __init__(self):
        self.status_code = 403
        self.detail = 'Search not allowed'


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
