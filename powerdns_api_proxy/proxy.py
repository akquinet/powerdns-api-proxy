import os
import json
from contextlib import asynccontextmanager
from http import HTTPStatus
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    Header,
    HTTPException,
    Request,
    Response,
)
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from starlette.exceptions import HTTPException as StarletteHTTPException

from powerdns_api_proxy.config import (
    check_pdns_search_allowed,
    check_pdns_cryptokeys_allowed,
    check_pdns_tsigkeys_allowed,
    check_pdns_zone_admin,
    check_pdns_zone_allowed,
    dependency_check_token_defined,
    dependency_metrics_proxy_enabled,
    ensure_rrsets_request_allowed,
    get_environment_for_token,
    get_only_pdns_zones_allowed,
    load_config,
)
from powerdns_api_proxy.exceptions import (
    RessourceNotAllowedException,
    SearchNotAllowedException,
    ZoneAdminNotAllowedException,
    ZoneNotAllowedException,
    UpstreamException,
)
from powerdns_api_proxy.logging import logger
from powerdns_api_proxy.metrics import http_requests_total_environment
from powerdns_api_proxy.models import (
    ResponseAllowed,
    ResponseZoneAllowed,
)
from powerdns_api_proxy.pdns import PDNSConnector, handle_pdns_response
from powerdns_api_proxy.audit import AuditLogger

if os.getenv("SENTRY_DSN"):
    import sentry_sdk
    from sentry_sdk.integrations.aiohttp import AioHttpIntegration
    from sentry_sdk.integrations.fastapi import FastApiIntegration

    sentry_sdk.init(
        traces_sample_rate=float(os.getenv("SENTRY_TRACES_SAMPLE_RATE") or 0.1),
        environment=os.getenv("ENVIRONMENT") or "DEV",
        integrations=[FastApiIntegration(), AioHttpIntegration()],
    )

# load config to verify it is valid
config = load_config()

pdns = PDNSConnector(
    config.pdns_api_url, config.pdns_api_token, config.pdns_api_verify_ssl
)

audit_logger = AuditLogger(config.audit_log_path)


@asynccontextmanager
async def _startup(app: FastAPI):
    yield


app = FastAPI(title="PowerDNS API Proxy", version="0.1.0", lifespan=_startup)

if not config.api_docs_enabled:
    logger.info("Disabling API docs")
    app = FastAPI(
        title=app.title,
        version=app.version,
        lifespan=_startup,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

if config.metrics_enabled:
    instrumentator = Instrumentator(
        should_group_status_codes=False,
    )
    logger.info("Enabling metrics")
    instrumentator.add(metrics.default())
    instrumentator.add(http_requests_total_environment())
    instrumentator.instrument(app)

    if config.metrics_require_auth:
        logger.info("Enabling metrics authentication")
        instrumentator.expose(
            app, dependencies=[Depends(dependency_metrics_proxy_enabled)]
        )
    else:
        instrumentator.expose(app)
else:
    logger.info("Metrics are disabled")


# Patching HTTPException to be compatible with PowerDNS API errors
# https://doc.powerdns.com/authoritative/http-api/index.html#errors
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse({"error": exc.detail}, status_code=exc.status_code)


router_proxy = APIRouter(
    prefix="/info",
    tags=["Information"],
    dependencies=[Depends(dependency_check_token_defined)],
)
router_health = APIRouter(
    prefix="/health",
    tags=["Information"],
)
router_pdns = APIRouter(
    prefix="/api/v1",
    tags=["PowerDNS Ressources"],
    dependencies=[Depends(dependency_check_token_defined)],
)


@app.head("/", include_in_schema=False)
@app.get("/", response_class=HTMLResponse, include_in_schema=False)
async def hello():
    if config.index_enabled:
        return config.index_html
    else:
        return HTMLResponse(status_code=404)


@router_health.get("/pdns", status_code=HTTPStatus.OK)
async def health_upstream_pdns_api(response: Response):
    """Checks connection to Upstream PowerDNS API."""
    logger.info("Checking upstream pdns api health")
    req = await pdns.get("/api/v1/servers")
    response.status_code = req.status
    data = {"details": "Upstream PowerDNS API seems to work :)"}
    if req.status != 200:
        data = {"details": "Something is wrong :(. Please help me!"}
        response.status_code = 500
    return data


@router_proxy.get(
    "/allowed",
    response_model=ResponseAllowed,
)
async def get_allowed_ressources(X_API_Key: str = Header()):
    """Retrieve allowed requests for the given token."""
    logger.info("Checking allowed ressources for given api key")
    environment = get_environment_for_token(config, X_API_Key)
    return ResponseAllowed(zones=environment.zones)


@router_proxy.get(
    "/zone-allowed",
    response_model=ResponseZoneAllowed,
)
async def get_zone_allowed(zone: str, X_API_Key: str = Header()):
    """
    Check if the given zone is allowed for the given token.
    Also returns the zone config that allows the zone.
    """
    logger.debug("Checking if zone is allowed for given api key")
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone):
        return ResponseZoneAllowed(zone=zone, allowed=False)

    zone_config = environment.get_zone_if_allowed(zone)
    return ResponseZoneAllowed(zone=zone, allowed=True, config=zone_config)


@router_proxy.get("/audit-log")
async def get_audit_log(
    environment: str | None = None,
    method: str | None = None,
    status_code: int | None = None,
    limit: int = 100,
    X_API_Key: str = Header(),
):
    """
    Retrieve audit log entries with optional filtering.
    Requires global_audit_log_access permission.
    """
    env = get_environment_for_token(config, X_API_Key)
    if not env.global_audit_log_access:
        audit_logger.log_change(env.name, "GET", "/info/audit-log", None, 403)
        raise HTTPException(403, "Audit log access not allowed")

    entries: list[dict] = []
    with open(config.audit_log_path) as f:
        for line in f:
            if len(entries) >= limit:
                break
            try:
                entry = json.loads(line)
                if environment and entry.get("environment") != environment:
                    continue
                if method and entry.get("method") != method:
                    continue
                if status_code and entry.get("status_code") != status_code:
                    continue
                entries.append(entry)
            except json.JSONDecodeError:
                continue

    return JSONResponse(content=entries)


@app.get("/api", dependencies=[Depends(dependency_check_token_defined)])
async def api_root():
    """Returns the version and a info that this is a proxy."""
    return [
        {
            "url": "/api/v1",
            "version": 1,
            "compatibility": "PowerDNS API Proxy, PowerDNS API v1",
        }
    ]


@router_pdns.get("/servers")
async def get_servers():
    """
    Retrieve a list of servers which can be used.

    <https://doc.powerdns.com/authoritative/http-api/server.html>
    """
    req = await pdns.get("/api/v1/servers")
    pdns_response = await handle_pdns_response(req)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get("/servers/{server_id}")
async def get_server(server_id: str):
    """
    Retrieve a specific server.

    <https://doc.powerdns.com/authoritative/http-api/server.html>
    """
    resp = await pdns.get(f"/api/v1/servers/{server_id}")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get(
    "/servers/{server_id}/configuration",
)
async def get_configuration(server_id: str):
    """
    Retrieve a list of configuration items for the server.
    Currently returns empty, as we don't want to expose the global backend configuration.
    """
    _ = server_id
    raise RessourceNotAllowedException()


@router_pdns.get(
    "/servers/{server_id}/statistics",
)
async def get_statistics(
    server_id: str,
):
    """
    Retrieve a list of statistics about the server.
    Currently returns empty, as we don't want to expose the global backend statistics.

    <https://doc.powerdns.com/authoritative/http-api/statistics.html#get--servers-server_id-statistics>
    """
    _ = server_id
    raise RessourceNotAllowedException()


@router_pdns.get(
    "/servers/{server_id}/zones",
)
async def get_zones(
    request: Request,
    server_id: str,
    X_API_Key: str = Header(),
):
    """
    Retrieve a list of zones that exist and belong to this account.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#get--servers-server_id-zones>
    """
    environment = get_environment_for_token(config, X_API_Key)
    resp = await pdns.get(
        f"/api/v1/servers/{server_id}/zones", dict(request.query_params)
    )
    pdns_response = await handle_pdns_response(resp)

    status_code = pdns_response.raise_for_error()

    if isinstance(pdns_response.data, list):
        filtered_data = get_only_pdns_zones_allowed(environment, pdns_response.data)
        return JSONResponse(content=filtered_data, status_code=status_code)
    else:
        logger.error(
            f"We expected powerdns to return json, it returned a string: {pdns_response.data}"
        )
        raise UpstreamException()


@router_pdns.post("/servers/{server_id}/zones")
async def create_zone(request: Request, server_id: str, X_API_Key: str = Header()):
    """
    Create a new zone.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#post--servers-server_id-zones>
    """
    payload = await request.json()
    logger.info(f'Zone creation request data: "{payload}"')
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, payload["name"]):
        audit_logger.log_change(
            environment.name, "POST", f"/zones/{payload['name']}", payload, 403
        )
        raise ZoneNotAllowedException()
    if not check_pdns_zone_admin(environment, payload["name"]):
        audit_logger.log_change(
            environment.name, "POST", f"/zones/{payload['name']}", payload, 403
        )
        raise ZoneAdminNotAllowedException()
    resp = await pdns.post(f"/api/v1/servers/{server_id}/zones", payload)
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "POST", f"/zones/{payload['name']}", payload, status_code
    )

    # POST typically returns 201 Created
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get(
    "/servers/{server_id}/zones/{zone_id}",
)
async def get_zone_metadata(
    request: Request,
    server_id: str,
    zone_id: str,
    X_API_Key: str = Header(),
):
    """
    Retrieve zone metadata.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#get--servers-server_id-zones-zone_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f"Zone {zone_id} not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.get(
        f"/api/v1/servers/{server_id}/zones/{zone_id}",
        params=dict(request.query_params),
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.put("/servers/{server_id}/zones/{zone_id}")
async def update_zone_metadata(
    request: Request,
    server_id: str,
    zone_id: str,
    X_API_Key: str = Header(),
):
    """
    Update zone metadata.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#put--servers-server_id-zones-zone_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    payload = await request.json()
    if not check_pdns_zone_allowed(environment, zone_id):
        audit_logger.log_change(
            environment.name, "PUT", f"/zones/{zone_id}", payload, 403
        )
        raise ZoneNotAllowedException()
    if not check_pdns_zone_admin(environment, zone_id):
        audit_logger.log_change(
            environment.name, "PUT", f"/zones/{zone_id}", payload, 403
        )
        raise ZoneAdminNotAllowedException()
    resp = await pdns.put(
        f"/api/v1/servers/{server_id}/zones/{zone_id}",
        payload=payload,
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "PUT", f"/zones/{zone_id}", payload, status_code
    )

    if status_code == HTTPStatus.NO_CONTENT:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.patch("/servers/{server_id}/zones/{zone_id}")
async def update_zone_rrset(
    request: Request,
    server_id: str,
    zone_id: str,
    X_API_Key: str = Header(),
):
    """
    Update RRSets of a zone.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#patch--servers-server_id-zones-zone_id>
    """
    logger.debug(f"Update RRSet request for {zone_id}")
    environment = get_environment_for_token(config, X_API_Key)
    payload = await request.json()
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f"Zone {zone_id} not allowed for environment {environment.name}")
        audit_logger.log_change(
            environment.name, "PATCH", f"/zones/{zone_id}", payload, 403
        )
        raise ZoneNotAllowedException()
    zone = environment.get_zone_if_allowed(zone_id)
    try:
        ensure_rrsets_request_allowed(zone, payload)
    except HTTPException:
        audit_logger.log_change(
            environment.name, "PATCH", f"/zones/{zone_id}", payload, 403
        )
        raise
    resp = await pdns.patch(
        f"/api/v1/servers/{server_id}/zones/{zone_id}",
        payload=payload,
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "PATCH", f"/zones/{zone_id}", payload, status_code
    )

    if status_code == HTTPStatus.NO_CONTENT:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.delete("/servers/{server_id}/zones/{zone_id}")
async def delete_zone(server_id: str, zone_id: str, X_API_Key: str = Header()):
    """
    Delete a zone immediately.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#delete--servers-server_id-zones-zone_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_admin(environment, zone_id):
        audit_logger.log_change(
            environment.name, "DELETE", f"/zones/{zone_id}", None, 403
        )
        raise ZoneNotAllowedException()
    resp = await pdns.delete(f"/api/v1/servers/{server_id}/zones/{zone_id}")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "DELETE", f"/zones/{zone_id}", None, status_code
    )

    # DELETE operations often return 204 No Content
    if status_code == HTTPStatus.NO_CONTENT:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.put("/servers/{server_id}/zones/{zone_id}/notify")
async def zone_notification(server_id: str, zone_id: str, X_API_Key: str = Header()):
    """
    Queue a zone for notification to replicas.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#put--servers-server_id-zones-zone_id-notify>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f"Zone {zone_id} not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.put(f"/api/v1/servers/{server_id}/zones/{zone_id}/notify")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    # PUT operations often return 204 No Content
    if status_code == HTTPStatus.NO_CONTENT:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.put("/servers/{server_id}/zones/{zone_id}/rectify")
async def zone_rectification(
    response: Response, server_id: str, zone_id: str, X_API_Key: str = Header()
):
    """
    Rectify the zone data.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#put--servers-server_id-zones-zone_id-rectify>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f"Zone {zone_id} not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.put(f"/api/v1/servers/{server_id}/zones/{zone_id}/rectify")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    # PUT operations often return 204 No Content
    if status_code == HTTPStatus.NO_CONTENT:
        return Response(status_code=HTTPStatus.NO_CONTENT)

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get("/servers/{server_id}/search-data")
async def search_data(
    server_id: str,
    q: str,
    max: int | None = None,
    object_type: Literal["all", "zone", "record", "comment"] = "all",
    X_API_Key: str = Header(),
):
    """
    Search the data inside PowerDNS

    Search the data inside PowerDNS for search_term
    and return at most max_results.
    This includes zones, records and comments.

    The * character can be used in search_term as a wildcard character
    and the ? character can be used as a wildcard for a single character.

    <https://doc.powerdns.com/authoritative/http-api/search.html>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_search_allowed(environment, q, object_type):
        logger.info(
            f'Search "{q}" with object_type "{object_type}" is not allowed '
            f"for environment {environment.name}"
        )
        raise SearchNotAllowedException()

    search_params: dict[str, str | int] = {"q": q, "object_type": object_type}
    if max is not None:
        search_params["max"] = max
    resp = await pdns.get(
        f"/api/v1/servers/{server_id}/search-data", params=search_params
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get("/servers/{server_id}/zones/{zone_id}/cryptokeys")
async def list_cryptokeys(server_id: str, zone_id: str, X_API_Key: str = Header()):
    """
    Get all CryptoKeys for a zone, except the private key.

    <https://doc.powerdns.com/authoritative/http-api/cryptokey.html#get--servers-server_id-zones-zone_id-cryptokeys>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_cryptokeys_allowed(environment, zone_id):
        logger.info(f"CryptoKeys not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.get(f"/api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.post("/servers/{server_id}/zones/{zone_id}/cryptokeys")
async def create_cryptokey(
    request: Request, server_id: str, zone_id: str, X_API_Key: str = Header()
):
    """
    Creates a Cryptokey.

    This method adds a new key to a zone.

    <https://doc.powerdns.com/authoritative/http-api/cryptokey.html#post--servers-server_id-zones-zone_id-cryptokeys>
    """
    environment = get_environment_for_token(config, X_API_Key)
    payload = await request.json()
    if not check_pdns_cryptokeys_allowed(environment, zone_id):
        logger.info(f"CryptoKeys not allowed for environment {environment.name}")
        audit_logger.log_change(
            environment.name, "POST", f"/zones/{zone_id}/cryptokeys", payload, 403
        )
        raise ZoneNotAllowedException()
    resp = await pdns.post(
        f"/api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys",
        payload=payload,
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "POST", f"/zones/{zone_id}/cryptokeys", payload, status_code
    )

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get("/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}")
async def fetch_cryptokey(
    server_id: str, zone_id: str, cryptokey_id: str, X_API_Key: str = Header()
):
    """
    Returns all data about the CryptoKey, including the private key.

    <https://doc.powerdns.com/authoritative/http-api/cryptokey.html#get--servers-server_id-zones-zone_id-cryptokeys-cryptokey_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_cryptokeys_allowed(environment, zone_id):
        logger.info(f"CryptoKeys not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.get(
        f"/api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}"
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.put("/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}")
async def update_cryptokey(
    request: Request,
    server_id: str,
    zone_id: str,
    cryptokey_id: str,
    X_API_Key: str = Header(),
):
    """
    This method (de)activates a key from zone_name specified by cryptokey_id.

    <https://doc.powerdns.com/authoritative/http-api/cryptokey.html#put--servers-server_id-zones-zone_id-cryptokeys-cryptokey_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    payload = await request.json()
    if not check_pdns_cryptokeys_allowed(environment, zone_id):
        logger.info(f"CryptoKeys not allowed for environment {environment.name}")
        audit_logger.log_change(
            environment.name,
            "PUT",
            f"/zones/{zone_id}/cryptokeys/{cryptokey_id}",
            payload,
            403,
        )
        raise ZoneNotAllowedException()
    resp = await pdns.put(
        f"/api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}",
        payload=payload,
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name,
        "PUT",
        f"/zones/{zone_id}/cryptokeys/{cryptokey_id}",
        payload,
        status_code,
    )

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.delete("/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}")
async def delete_cryptokey(
    server_id: str, zone_id: str, cryptokey_id: str, X_API_Key: str = Header()
):
    """
    This method deletes a key specified by cryptokey_id.

    <https://doc.powerdns.com/authoritative/http-api/cryptokey.html#delete--servers-server_id-zones-zone_id-cryptokeys-cryptokey_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_cryptokeys_allowed(environment, zone_id):
        logger.info(f"CryptoKeys not allowed for environment {environment.name}")
        audit_logger.log_change(
            environment.name,
            "DELETE",
            f"/zones/{zone_id}/cryptokeys/{cryptokey_id}",
            None,
            403,
        )
        raise ZoneNotAllowedException()
    resp = await pdns.delete(
        f"/api/v1/servers/{server_id}/zones/{zone_id}/cryptokeys/{cryptokey_id}"
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name,
        "DELETE",
        f"/zones/{zone_id}/cryptokeys/{cryptokey_id}",
        None,
        status_code,
    )

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get("/servers/{server_id}/tsigkeys")
async def list_tsigkeys(server_id: str, X_API_Key: str = Header()):
    """
    Get all TSIGKeys on the server, except the actual key.

    <https://doc.powerdns.com/authoritative/http-api/tsigkey.html#get--servers-server_id-tsigkeys>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_tsigkeys_allowed(environment):
        logger.info(f"TSIGKeys not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.get(f"/api/v1/servers/{server_id}/tsigkeys")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.get("/servers/{server_id}/tsigkeys/{tsigkey_id}")
async def fetch_tsigkey(server_id: str, tsigkey_id: str, X_API_Key: str = Header()):
    """
    Get a specific TSIGKeys on the server, including the actual key.

    <https://doc.powerdns.com/authoritative/http-api/tsigkey.html#get--servers-server_id-tsigkeys-tsigkey_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_tsigkeys_allowed(environment):
        logger.info(f"TSIGKeys not allowed for environment {environment.name}")
        raise ZoneNotAllowedException()
    resp = await pdns.get(f"/api/v1/servers/{server_id}/tsigkeys/{tsigkey_id}")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()
    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.post("/servers/{server_id}/tsigkeys")
async def create_tsigkey(request: Request, server_id: str, X_API_Key: str = Header()):
    """
    Add a TSIG key.

    This methods add a new TSIGKey. The actual key can be generated by the server or
    be provided by the client.

    <https://doc.powerdns.com/authoritative/http-api/tsigkey.html#post--servers-server_id-tsigkeys>
    """
    environment = get_environment_for_token(config, X_API_Key)
    payload = await request.json()
    if not check_pdns_tsigkeys_allowed(environment):
        logger.info(f"TSIGKeys not allowed for environment {environment.name}")
        audit_logger.log_change(environment.name, "POST", "/tsigkeys", payload, 403)
        raise ZoneNotAllowedException()
    resp = await pdns.post(f"/api/v1/servers/{server_id}/tsigkeys", payload=payload)
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(environment.name, "POST", "/tsigkeys", payload, status_code)

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.put("/servers/{server_id}/tsigkeys/{tsigkey_id}")
async def update_tsigkey(
    request: Request,
    server_id: str,
    tsigkey_id: str,
    X_API_Key: str = Header(),
):
    """
    The TSIGKey at tsigkey_id can be changed in multiple ways:

    * Changing the Name, this will remove the key with tsigkey_id after adding.
    * Changing the Algorithm
    * Changing the Key

    Only the relevant fields have to be provided in the request body.

    <https://doc.powerdns.com/authoritative/http-api/tsigkey.html#put--servers-server_id-tsigkeys-tsigkey_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    payload = await request.json()
    if not check_pdns_tsigkeys_allowed(environment):
        logger.info(f"TSIGKeys not allowed for environment {environment.name}")
        audit_logger.log_change(
            environment.name, "PUT", f"/tsigkeys/{tsigkey_id}", payload, 403
        )
        raise ZoneNotAllowedException()
    resp = await pdns.put(
        f"/api/v1/servers/{server_id}/tsigkeys/{tsigkey_id}",
        payload=payload,
    )
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "PUT", f"/tsigkeys/{tsigkey_id}", payload, status_code
    )

    return JSONResponse(content=pdns_response.data, status_code=status_code)


@router_pdns.delete("/servers/{server_id}/tsigkeys/{tsigkey_id}")
async def delete_tsigkey(server_id: str, tsigkey_id: str, X_API_Key: str = Header()):
    """
    Delete the TSIGKey with tsigkey_id.

    <https://doc.powerdns.com/authoritative/http-api/tsigkey.html#delete--servers-server_id-tsigkeys-tsigkey_id>
    """
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_tsigkeys_allowed(environment):
        logger.info(f"TSIGKeys not allowed for environment {environment.name}")
        audit_logger.log_change(
            environment.name, "DELETE", f"/tsigkeys/{tsigkey_id}", None, 403
        )
        raise ZoneNotAllowedException()
    resp = await pdns.delete(f"/api/v1/servers/{server_id}/tsigkeys/{tsigkey_id}")
    pdns_response = await handle_pdns_response(resp)
    status_code = pdns_response.raise_for_error()

    audit_logger.log_change(
        environment.name, "DELETE", f"/tsigkeys/{tsigkey_id}", None, status_code
    )

    return JSONResponse(content=pdns_response.data, status_code=status_code)


app.include_router(router_proxy)
app.include_router(router_pdns)
app.include_router(router_health)
