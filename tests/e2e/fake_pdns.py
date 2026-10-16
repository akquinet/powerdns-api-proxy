"""Fake PowerDNS API upstream used by the end-to-end tests.

The app runs in a background thread on 127.0.0.1 and serves canned payloads.
Every request is recorded so tests can assert what actually reached upstream.
"""

import asyncio
import threading
import time
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from aiohttp import web

Handler = Callable[[web.Request], Awaitable[web.StreamResponse]]

ZONES: list[dict[str, Any]] = [
    {"name": "managed.example.com.", "kind": "Native"},
    {"name": "other.example.com.", "kind": "Native"},
    {"name": "plain.example.com.", "kind": "Native"},
    {"name": "ro.example.com.", "kind": "Native"},
    {"name": "writable.example.com.", "kind": "Native"},
]

UNKNOWN_ZONE = "unknown.example.com."


class FakePowerDNS:
    """Minimal PowerDNS API double recording every request it receives."""

    def __init__(self, port: int) -> None:
        self.port = port
        self.requests: list[tuple[str, str]] = []
        self._loop: asyncio.AbstractEventLoop | None = None
        self._runner: web.AppRunner | None = None
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def _make_app(self) -> web.Application:
        app = web.Application(middlewares=[self._record])
        app.router.add_get("/__ready", self._ready)
        app.router.add_get("/api/v1/servers", self._get_servers)
        app.router.add_get("/api/v1/servers/{server}/zones", self._get_zones)
        app.router.add_get("/api/v1/servers/{server}/zones/{zone}", self._get_zone)
        app.router.add_patch("/api/v1/servers/{server}/zones/{zone}", self._no_content)
        app.router.add_delete("/api/v1/servers/{server}/zones/{zone}", self._no_content)
        app.router.add_put(
            "/api/v1/servers/{server}/zones/{zone}/notify", self._no_content
        )
        app.router.add_put(
            "/api/v1/servers/{server}/zones/{zone}/rectify", self._no_content
        )
        return app

    @web.middleware
    async def _record(
        self, request: web.Request, handler: Handler
    ) -> web.StreamResponse:
        if request.path != "/__ready":
            self.requests.append((request.method, request.path))
        return await handler(request)

    async def _ready(self, request: web.Request) -> web.Response:
        return web.json_response({"ready": True})

    async def _get_servers(self, request: web.Request) -> web.Response:
        return web.json_response(
            [{"id": "localhost", "url": "/api/v1/servers/localhost"}]
        )

    async def _get_zones(self, request: web.Request) -> web.Response:
        return web.json_response(ZONES)

    async def _get_zone(self, request: web.Request) -> web.Response:
        zone = request.match_info["zone"]
        if zone == UNKNOWN_ZONE:
            return web.json_response({"error": "Not Found"}, status=404)
        return web.json_response({"name": zone, "kind": "Native", "rrsets": []})

    async def _no_content(self, request: web.Request) -> web.Response:
        return web.Response(status=204)

    def received(self, method: str, path: str) -> bool:
        return (method, path) in self.requests

    async def _start(self) -> None:
        self._runner = web.AppRunner(self._make_app())
        await self._runner.setup()
        await web.TCPSite(self._runner, "127.0.0.1", self.port).start()

    def start(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop

        def run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._start())
            loop.run_forever()

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def wait_ready(self, timeout: float = 10.0) -> None:
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            try:
                if httpx.get(f"{self.url}/__ready", timeout=1).status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.05)
        raise RuntimeError("fake PowerDNS upstream did not become ready")

    def stop(self) -> None:
        if self._loop is None:
            return
        if self._runner is not None:
            future = asyncio.run_coroutine_threadsafe(
                self._runner.cleanup(), self._loop
            )
            future.result(timeout=5)
        self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5)
        self._loop.close()
