import logging
import logging.handlers
from os import getenv
from sys import stderr

LOG_LEVEL = getenv("LOG_LEVEL") or "DEBUG"

logging_format = (
    "%(levelname)s - %(asctime)s - %(name)s - "
    + "%(filename)s - %(funcName)s - %(lineno)s - %(message)s"
)

default_formatter = logging.Formatter(logging_format)

default_stream_handler = logging.StreamHandler(stderr)
default_stream_handler.setLevel(LOG_LEVEL)
default_stream_handler.setFormatter(default_formatter)

file_handler = logging.handlers.RotatingFileHandler(
    filename="log", maxBytes=1000**2 * 100, backupCount=5
)
file_handler.setLevel("DEBUG")
file_handler.setFormatter(default_formatter)

logger = logging.getLogger("powerdns_api_proxy")
logger.addHandler(default_stream_handler)
logger.addHandler(file_handler)

logger.setLevel("DEBUG")
