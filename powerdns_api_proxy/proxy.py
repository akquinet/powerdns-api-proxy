import os
from http import HTTPStatus
from typing import Literal

import sentry_sdk
from fastapi import APIRouter, Depends, FastAPI, Header, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse
from prometheus_fastapi_instrumentator import Instrumentator, metrics
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from sentry_sdk.integrations.fastapi import FastApiIntegration
from starlette.exceptions import HTTPException as StarletteHTTPException

from powerdns_api_proxy.config import (
    check_pdns_search_allowed,
    check_pdns_zone_admin,
    check_pdns_zone_allowed,
    dependency_check_token_defined,
    ensure_rrsets_request_allowed,
    get_environment_for_token,
    get_only_pdns_zones_allowed,
    load_config,
)
from powerdns_api_proxy.logging import logger
from powerdns_api_proxy.metrics import http_requests_total_environment
from powerdns_api_proxy.models import (
    ResponseAllowed,
    RessourceNotAllowedException,
    SearchNotAllowedException,
    ZoneAdminNotAllowedException,
    ZoneNotAllowedException,
)
from powerdns_api_proxy.pdns import PDNSConnector
from powerdns_api_proxy.utils import response_json_or_text

if os.getenv('SENTRY_DSN'):
    sentry_sdk.init(
        traces_sample_rate=float(os.getenv('SENTRY_TRACES_SAMPLE_RATE') or 0.1),
        environment=os.getenv('ENVIRONMENT') or 'DEV',
        integrations=[FastApiIntegration(), AioHttpIntegration()],
    )

# load config to verify it is valid
config = load_config()

pdns = PDNSConnector(
    config.pdns_api_url, config.pdns_api_token, config.pdns_api_verify_ssl
)

app = FastAPI(title='PowerDNS API Proxy', version='0.1.0')
instrumentator = Instrumentator(
    should_group_status_codes=False,
)
instrumentator.add(metrics.default())
instrumentator.instrument(app)


@app.on_event('startup')
async def _startup():
    instrumentator.add(http_requests_total_environment())
    instrumentator.expose(app)


# Patching HTTPException to be compatible with PowerDNS API errors
# https://doc.powerdns.com/authoritative/http-api/index.html#errors
@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse({'error': exc.detail}, status_code=exc.status_code)


router_proxy = APIRouter(
    prefix='/info',
    tags=['Information'],
    dependencies=[Depends(dependency_check_token_defined)],
)
router_health = APIRouter(
    prefix='/health',
    tags=['Information'],
)
router_pdns = APIRouter(
    prefix='/api/v1',
    tags=['PowerDNS Ressources'],
    dependencies=[Depends(dependency_check_token_defined)],
)


@app.head('/', include_in_schema=False)
@app.get('/', response_class=HTMLResponse, include_in_schema=False)
async def hello():
    return '''
    <html>
        <head>
            <title>PowerDNS API Proxy</title>
        </head>
        <body>
            <center>
            <h1>PowerDNS API Proxy</h1>
            <p>| <a href="/docs">Swagger Docs</a></p>
            <q>The Domain Name Server (DNS) is the Achilles heel of the Web.<br>
            The important thing is that it's managed responsibly.</q>
            </center>
        </body>
    </html>
'''


@router_health.get('/pdns', status_code=HTTPStatus.OK)
async def health_upstream_pdns_api(response: Response):
    '''Checks connection to Upstream PowerDNS API.'''
    logger.info('Checking upstream pdns api health')
    req = await pdns.get('/api/v1/servers')
    response.status_code = req.status
    data = {'details': 'Upstream PowerDNS API seems to work :)'}
    if req.status != 200:
        data = {'details': 'Something is wrong :(. Please help me!'}
        response.status_code = 500
    return data


@router_proxy.get(
    '/allowed',
    response_model=ResponseAllowed,
)
async def get_allowed_ressources(X_API_Key: str = Header()):
    '''Retrieve allowed requests for the given token.'''
    logger.info('Checking allowed ressources for given api key')
    environment = get_environment_for_token(config, X_API_Key)
    return ResponseAllowed(zones=environment.zones)


@app.get('/api', dependencies=[Depends(dependency_check_token_defined)])
async def api_root():
    '''Returns the version and a info that this is a proxy.'''
    return [
        {
            'url': '/api/v1',
            'version': 1,
            'compatibility': 'PowerDNS API Proxy, PowerDNS API v1',
        }
    ]


@router_pdns.get('/servers')
async def get_servers(response: Response):
    '''
    Retrieve a list of servers which can be used.

    <https://doc.powerdns.com/authoritative/http-api/server.html>
    '''
    req = await pdns.get('/api/v1/servers')
    data = await req.json()
    response.status_code = req.status
    return data


@router_pdns.get('/servers/{server_id}')
async def get_server(response: Response, server_id: str):
    '''
    Retrieve a specific server.

    <https://doc.powerdns.com/authoritative/http-api/server.html>
    '''
    resp = await pdns.get(f'/api/v1/servers/{server_id}')
    data = await response_json_or_text(resp)
    response.status_code = resp.status
    return data


@router_pdns.get(
    '/servers/{server_id}/configuration',
)
async def get_configuration(server_id: str):
    '''
    Retrieve a list of configuration items for the server.
    Currently returns empty, as we don't want to expose the global backend configuration.
    '''
    _ = server_id
    raise RessourceNotAllowedException()


@router_pdns.get(
    '/servers/{server_id}/statistics',
)
async def get_statistics(
    server_id: str,
):
    '''
    Retrieve a list of statistics about the server.
    Currently returns empty, as we don't want to expose the global backend statistics.

    <https://doc.powerdns.com/authoritative/http-api/statistics.html#get--servers-server_id-statistics>
    '''
    _ = server_id
    raise RessourceNotAllowedException()


@router_pdns.get(
    '/servers/{server_id}/zones',
)
async def get_zones(
    request: Request,
    response: Response,
    server_id: str,
    X_API_Key: str = Header(),
):
    '''
    Retrieve a list of zones that exist and belong to this account.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#get--servers-server_id-zones>
    '''
    environment = get_environment_for_token(config, X_API_Key)
    resp = await pdns.get(
        f'/api/v1/servers/{server_id}/zones', dict(request.query_params)
    )
    response.status_code = resp.status
    zones = await resp.json()
    return get_only_pdns_zones_allowed(environment, zones)


@router_pdns.post(
    '/servers/{server_id}/zones',
)
async def create_zone(
    request: Request, response: Response, server_id: str, X_API_Key: str = Header()
):
    '''
    Create a new zone.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#post--servers-server_id-zones>
    '''
    payload = await request.json()
    logger.info(f'Zone creation request data: "{payload}"')
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, payload['name']):
        raise ZoneNotAllowedException()
    if not check_pdns_zone_admin(environment, payload['name']):
        raise ZoneAdminNotAllowedException()
    resp = await pdns.post(f'/api/v1/servers/{server_id}/zones', payload)
    response.status_code = resp.status
    data = await response_json_or_text(resp)
    return data


@router_pdns.get(
    '/servers/{server_id}/zones/{zone_id}',
)
async def get_zone_metadata(
    request: Request,
    response: Response,
    server_id: str,
    zone_id: str,
    X_API_Key: str = Header(),
):
    '''
    Retrieve zone metadata.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#get--servers-server_id-zones-zone_id>
    '''
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f'Zone {zone_id} not allowed for environment {environment.name}')
        raise ZoneNotAllowedException()
    resp = await pdns.get(
        f'/api/v1/servers/{server_id}/zones/{zone_id}',
        params=dict(request.query_params),
    )
    response.status_code = resp.status
    data = await response_json_or_text(resp)
    return data


@router_pdns.put('/servers/{server_id}/zones/{zone_id}')
async def update_zone_metadata(
    request: Request,
    response: Response,
    server_id: str,
    zone_id: str,
    X_API_Key: str = Header(),
):
    '''
    Update zone metadata.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#put--servers-server_id-zones-zone_id>
    '''
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        raise ZoneNotAllowedException()
    if not check_pdns_zone_admin(environment, zone_id):
        raise ZoneAdminNotAllowedException()
    resp = await pdns.put(
        f'/api/v1/servers/{server_id}/zones/{zone_id}',
        payload=await request.json(),
    )
    response.status_code = resp.status
    if response.status_code != HTTPStatus.NO_CONTENT:
        data = await response_json_or_text(resp)
        return data
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router_pdns.patch('/servers/{server_id}/zones/{zone_id}')
async def update_zone_rrset(
    request: Request,
    response: Response,
    server_id: str,
    zone_id: str,
    X_API_Key: str = Header(),
):
    '''
    Update RRSets of a zone.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#patch--servers-server_id-zones-zone_id>
    '''
    logger.debug(f'Update RRSet request for {zone_id}')
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f'Zone {zone_id} not allowed for environment {environment.name}')
        raise ZoneNotAllowedException()
    zone = environment.get_zone_if_allowed(zone_id)
    ensure_rrsets_request_allowed(zone, await request.json())
    resp = await pdns.patch(
        f'/api/v1/servers/{server_id}/zones/{zone_id}',
        payload=await request.json(),
    )
    response.status_code = resp.status
    if response.status_code != HTTPStatus.NO_CONTENT:
        data = await response_json_or_text(resp)
        return data
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router_pdns.delete('/servers/{server_id}/zones/{zone_id}')
async def delete_zone(
    response: Response, server_id: str, zone_id: str, X_API_Key: str = Header()
):
    '''
    Delete a zone immediately.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#delete--servers-server_id-zones-zone_id>
    '''
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_admin(environment, zone_id):
        raise ZoneNotAllowedException()
    resp = await pdns.delete(f'/api/v1/servers/{server_id}/zones/{zone_id}')
    response.status_code = resp.status
    if response.status_code != HTTPStatus.NO_CONTENT:
        data = await response_json_or_text(resp)
        return data
    return Response(status_code=HTTPStatus.NO_CONTENT)


@router_pdns.put('/servers/{server_id}/zones/{zone_id}/notify')
async def zone_notification(
    response: Response, server_id: str, zone_id: str, X_API_Key: str = Header()
):
    '''
    Queue a zone for notification to replicas.

    <https://doc.powerdns.com/authoritative/http-api/zone.html#put--servers-server_id-zones-zone_id-notify>
    '''
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_zone_allowed(environment, zone_id):
        logger.info(f'Zone {zone_id} not allowed for environment {environment.name}')
        raise ZoneNotAllowedException()
    resp = await pdns.put(f'/api/v1/servers/{server_id}/zones/{zone_id}/notify')
    response.status_code = resp.status
    data = await response_json_or_text(resp)
    return data


@router_pdns.get('/servers/{server_id}/search-data')
async def search_data(
    response: Response,
    server_id: str,
    q: str,
    max: int | None = None,
    object_type: Literal['all', 'zone', 'record', 'comment'] = 'all',
    X_API_Key: str = Header(),
):
    '''
    Search the data inside PowerDNS

    Search the data inside PowerDNS for search_term
    and return at most max_results.
    This includes zones, records and comments.

    The * character can be used in search_term as a wildcard character
    and the ? character can be used as a wildcard for a single character.

    <https://doc.powerdns.com/authoritative/http-api/search.html>
    '''
    environment = get_environment_for_token(config, X_API_Key)
    if not check_pdns_search_allowed(environment, q, object_type):
        logger.info(
            f'Search "{q}" with object_type "{object_type}" is not allowed '
            f'for environment {environment.name}'
        )
        raise SearchNotAllowedException()

    search_params: dict[str, str | int] = {'q': q, 'object_type': object_type}
    if max is not None:
        search_params['max'] = max
    resp = await pdns.get(
        f'/api/v1/servers/{server_id}/search-data', params=search_params
    )
    response.status_code = resp.status
    data = await response_json_or_text(resp)
    return data


app.include_router(router_proxy)
app.include_router(router_pdns)
app.include_router(router_health)
