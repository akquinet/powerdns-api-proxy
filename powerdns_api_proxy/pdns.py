import aiohttp

from powerdns_api_proxy.logging import logger


class PDNSConnector:
    def __init__(self, url: str, token: str, verify_ssl: bool = True):
        self.base_url = url
        self.token = token
        self.verify_ssl = verify_ssl
        self.headers = {
            "Content-Type": "application/json",
            "X-API-Key": self.token,
        }

    async def request(
        self, method: str, path: str, params: dict = {}, payload: dict = {}
    ):
        logger.info(
            f"Getting upstream PDNS API with method: {method}, path: {self.base_url + path}, "
            f"params: {params}, payload: {payload}"
        )
        async with aiohttp.ClientSession(
            base_url=self.base_url,
            headers=self.headers,
            connector_owner=False,
        ) as session:
            async with session.request(
                method,
                url=path,
                params=params,
                json=payload,
                verify_ssl=self.verify_ssl,
            ) as req:
                text = await req.text()
                logger.debug(
                    f'Got answer from upstream PDNS API Status: {req.status}, text: "{text}"'
                )
                return req

    async def get(self, path: str, params: dict = {}) -> aiohttp.ClientResponse:
        return await self.request("GET", path, params=params)

    async def post(self, path: str, payload: dict = {}) -> aiohttp.ClientResponse:
        return await self.request("POST", path, payload=payload)

    async def put(self, path: str, payload: dict = {}) -> aiohttp.ClientResponse:
        return await self.request("PUT", path, payload=payload)

    async def patch(self, path: str, payload: dict = {}) -> aiohttp.ClientResponse:
        return await self.request("PATCH", path, payload=payload)

    async def delete(self, path: str, payload: dict = {}) -> aiohttp.ClientResponse:
        return await self.request("DELETE", path, payload=payload)
