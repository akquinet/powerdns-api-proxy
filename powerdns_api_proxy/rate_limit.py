import math
import os
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass

_TRUE_VALUES = {"true", "1", "yes", "on"}
_FALSE_VALUES = {"false", "0", "no", "off"}


def _parse_bool(name: str, raw: str, default: bool) -> bool:
    if raw == "":
        return default
    value = raw.lower()
    if value in _TRUE_VALUES:
        return True
    if value in _FALSE_VALUES:
        return False
    raise ValueError(
        f"{name} must be a boolean (true/false/1/0/yes/no/on/off), got {raw!r}"
    )


def _parse_positive_int(name: str, raw: str, default: int) -> int:
    if raw == "":
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}") from None
    if value <= 0:
        raise ValueError(f"{name} must be a positive integer, got {raw!r}")
    return value


@dataclass(frozen=True)
class RateLimitConfig:
    """Configuration for the failed authentication rate limiter."""

    enabled: bool = True
    auth_failures: int = 20
    window_seconds: int = 60

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "RateLimitConfig":
        source = os.environ if env is None else env
        defaults = cls()
        return cls(
            enabled=_parse_bool(
                "RATE_LIMIT_ENABLED",
                source.get("RATE_LIMIT_ENABLED", ""),
                defaults.enabled,
            ),
            auth_failures=_parse_positive_int(
                "RATE_LIMIT_AUTH_FAILURES",
                source.get("RATE_LIMIT_AUTH_FAILURES", ""),
                defaults.auth_failures,
            ),
            window_seconds=_parse_positive_int(
                "RATE_LIMIT_WINDOW_SECONDS",
                source.get("RATE_LIMIT_WINDOW_SECONDS", ""),
                defaults.window_seconds,
            ),
        )


@dataclass
class _FailureWindow:
    started: float
    failures: int


class AuthFailureRateLimiter:
    """Count failed token authentications per key in a fixed window.

    The state lives in this process and in memory. Running multiple workers
    multiplies the effective limit (each process keeps its own counters) and a
    restart clears every counter.
    """

    def __init__(
        self,
        config: RateLimitConfig,
        clock: Callable[[], float] = time.monotonic,
    ):
        self.config = config
        self._clock = clock
        self._windows: dict[str, _FailureWindow] = {}
        self._last_cleanup: float | None = None

    def retry_after(self, key: str) -> int | None:
        """Return the seconds to wait when blocked, or None when allowed."""
        if not self.config.enabled:
            return None

        window = self._windows.get(key)
        if window is None:
            return None

        elapsed = self._clock() - window.started
        if elapsed >= self.config.window_seconds:
            del self._windows[key]
            return None

        if window.failures < self.config.auth_failures:
            return None

        return max(1, math.ceil(self.config.window_seconds - elapsed))

    def record_failure(self, key: str) -> None:
        """Record a failed authentication, starting or extending its window."""
        if not self.config.enabled:
            return

        now = self._clock()
        self._cleanup(now)

        window = self._windows.get(key)
        if window is None or now - window.started >= self.config.window_seconds:
            self._windows[key] = _FailureWindow(started=now, failures=1)
        else:
            window.failures += 1

    def record_success(self, key: str) -> None:
        """Clear the failures for a key after a successful authentication."""
        self._windows.pop(key, None)

    def _cleanup(self, now: float) -> None:
        """Drop expired windows at most once per configured window."""
        if (
            self._last_cleanup is not None
            and now - self._last_cleanup < self.config.window_seconds
        ):
            return

        self._last_cleanup = now
        expired = [
            key
            for key, window in self._windows.items()
            if now - window.started >= self.config.window_seconds
        ]
        for key in expired:
            del self._windows[key]
