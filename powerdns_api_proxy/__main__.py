import os
import sys
import uvicorn
from powerdns_api_proxy.uvicorn_config import LOGGING_CONFIG


def main() -> int:
    host = os.getenv("LISTEN_HOST", "*")
    port = int(os.getenv("LISTEN_PORT", "8000"))
    reload = "--reload" in sys.argv

    uvicorn.run(
        "powerdns_api_proxy.proxy:app",
        host=host,
        port=port,
        log_config=LOGGING_CONFIG,
        reload=reload,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
