"""
SmartAPI Registry Integration

Handles interaction with the SmartAPI registry.
"""

import re

import httpx
from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.api.config import Config
from awslabs.openapi_mcp_server.utils.openapi import load_openapi_spec
from awslabs.openapi_mcp_server.utils.openapi_validator import validate_openapi_spec

smartapi_query_url = "https://smart-api.info/api/query?q={q}&fields=_id&size=500&raw=1"


async def get_smartapi_ids(q: str) -> list:
    """Give a query string, return a list of SmartAPI IDs matching the query."""
    _url = smartapi_query_url.format(q=q)

    smartapi_ids = []
    async with httpx.AsyncClient() as client:
        response = await client.get(_url)
        response.raise_for_status()
        data = response.json()
        for api in data["hits"]:
            smartapi_id = api["_id"]
            smartapi_ids.append(smartapi_id)
    return smartapi_ids


def load_api_spec(smartapi_id: str) -> dict:
    config = Config(
        api_spec_url=f"https://smart-api.info/api/metadata/{smartapi_id}",
    )
    api_spec = load_openapi_spec(url=config.api_spec_url)

    # Validate the OpenAPI spec
    if not validate_openapi_spec(api_spec):
        logger.warning("OpenAPI specification validation failed, but continuing anyway")

    return api_spec


def get_base_server_url(api_spec: dict) -> str:
    """Return the base server URL for the given API specification."""
    api_name = re.sub(r"[^a-z0-9_-]", "_", api_spec["info"]["title"].lower())
    base_server_url = None
    if len(api_spec["servers"]) == 1:
        base_server_url = api_spec["servers"][0]["url"]
    elif len(api_spec["servers"]) > 1:
        for server in api_spec["servers"]:
            server_desc = server.get("description", "")
            if "ci.transltr.io" in server["url"].lower():
                base_server_url = server["url"]
                break
            if (
                "Production server on https" in server_desc
                or "Production" in server_desc
            ):
                base_server_url = server["url"]
                break
    if not base_server_url:
        err_msg = "Cannot determine server URL for API: {}\n{}"
        err_msg = err_msg.format(api_name, api_spec["servers"])
        raise ValueError(err_msg)
    return base_server_url
