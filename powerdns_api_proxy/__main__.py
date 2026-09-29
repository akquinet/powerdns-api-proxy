import os
import sys
import uvicorn
from powerdns_api_proxy.uvicorn_config import LOGGING_CONFIG


def main() -> int:
    host = os.getenv("LISTEN_HOST", "*")
    port = int(os.getenv("LISTEN_PORT", "8000"))
    reload = "--reload" in sys.argv

    # Passed explicitly rather than relying on uvicorn's defaults: this is the
    # trust boundary that decides whether X-Forwarded-For is honoured, so it
    # should not silently change under us on a dependency bump.
    forwarded_allow_ips = os.getenv("FORWARDED_ALLOW_IPS", "127.0.0.1")

    uvicorn.run(
        "powerdns_api_proxy.proxy:app",
        host=host,
        port=port,
        log_config=LOGGING_CONFIG,
        reload=reload,
        proxy_headers=True,
        forwarded_allow_ips=forwarded_allow_ips,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
