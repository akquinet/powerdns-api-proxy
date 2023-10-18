from typing import Callable

from prometheus_client import REGISTRY, CollectorRegistry, Counter
from prometheus_fastapi_instrumentator.metrics import Info

from powerdns_api_proxy.config import get_environment_for_token, load_config

config = load_config()


def http_requests_total_environment(
    metric_namespace: str = '',
    metric_subsystem: str = '',
    registry: CollectorRegistry = REGISTRY,
) -> Callable[[Info], None]:
    '''
    This function is used to create a metric for the number of requests
    by environment, method, status and handler.
    '''
    METRIC = Counter(
        'http_requests_environment',
        'Total number of requests by environment, method, status and handler.',
        labelnames=('environment', 'method', 'status', 'handler'),
        namespace=metric_namespace,
        subsystem=metric_subsystem,
        registry=registry,
    )

    def instrumentation(info: Info) -> None:
        if info and 'X-API-Key' in info.request.headers:
            try:
                environment = get_environment_for_token(
                    config, info.request.headers['X-API-Key']
                )
            except ValueError:
                return
            METRIC.labels(
                environment=environment.name,
                method=info.method,
                status=info.modified_status,
                handler=info.modified_handler,
            ).inc()

    return instrumentation
