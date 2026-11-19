import os

# The proxy loads its configuration at import time, so point at the example
# config before any test module imports the app.
os.environ.setdefault("PROXY_CONFIG_PATH", "./config-example.yml")

# Many existing tests deliberately send wrong tokens. Disable the global rate
# limiter so their assertions keep seeing 401 instead of the default 20-failure
# 429. The rate limit tests install their own limiter explicitly.
os.environ["RATE_LIMIT_ENABLED"] = "false"
