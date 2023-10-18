import json
from json.decoder import JSONDecodeError
from typing import Union

from aiohttp import ClientResponse


async def response_json_or_text(response: ClientResponse) -> Union[dict, str]:
    '''Returns a `string` or a `dict` from the `ClientResponse`'''
    text = await response.text()
    try:
        return json.loads(text)
    except JSONDecodeError:
        return text
