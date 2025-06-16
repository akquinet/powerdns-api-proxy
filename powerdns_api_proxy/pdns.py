import json
import aiohttp
from json.decoder import JSONDecodeError
from typing import Any, Union

from fastapi import HTTPException

from powerdns_api_proxy.exceptions import UnhandledException, UpstreamException
from powerdns_api_proxy.logging import logger


# Type definitions for PowerDNS API responses
PDNSResponseStr = str
PDNSResponseList = list[Any]
PDNSResponseDict = dict[str, Any]
PDNSResponseData = Union[PDNSResponseStr, PDNSResponseList, PDNSResponseDict]


class PDNSResponse:
    """Class representing a response from the PowerDNS API"""

    def __init__(
        self, data: PDNSResponseData, status_code: int, url: str | None = None
    ):
        self.data = data
        self.status_code = status_code
        self.is_success = 200 <= status_code < 300
        self.url = url

    def raise_for_error(self) -> int:
        """
        Raise appropriate exception if this is an error response.

        Returns:
            The HTTP status code for successful responses
        """
        if self.is_success:
            return self.status_code

        # Forward common status codes directly
        if self.status_code in (400, 404, 409, 422):
            error_msg = (
                self.data.get("error", "Unknown error")
                if isinstance(self.data, dict)
                else str(self.data)
            )
            logger.error(f"PowerDNS error {self.status_code}: {error_msg}")
            raise HTTPException(status_code=self.status_code, detail=error_msg)

        # Handle other error cases
        if isinstance(self.data, dict) and "error" in self.data:
            error_msg = self.data.get("error", "Unknown error")
            logger.error(f"PowerDNS upstream error: {error_msg}")
            raise UpstreamException()
        else:
            error_msg = f"Unhandled PowerDNS error: {self.data}"
            logger.error(error_msg)
            raise UnhandledException()


async def response_json_or_text(response: aiohttp.ClientResponse) -> PDNSResponseData:
    """Returns a PowerDNS response (dict, list, or string) from the ClientResponse"""
    text = await response.text()
    try:
        return json.loads(text)
    except JSONDecodeError:
        return text


async def handle_pdns_response(pdns_response: aiohttp.ClientResponse) -> PDNSResponse:
    """
    Handle a response from the PowerDNS API.

    Args:
        pdns_response: The response from the PowerDNS API

    Returns:
        PDNSResponse object containing the response data and status
    """
    data = await response_json_or_text(pdns_response)
    response = PDNSResponse(data, pdns_response.status, str(pdns_response.url))
    return response


class PDNSConnector:
    def __init__(self, url: str, token: str, verify_ssl: bool = True):
        self.base_url = url
        self.token = token
        self.verify_ssl = verify_ssl
        self.headers = {
            "Accept": "application/json",
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
            base_url=self.base_url, headers=self.headers
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
