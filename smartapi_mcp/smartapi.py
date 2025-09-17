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


PREDEFINED_API_SETS = ["biothings_core", "biothings_test", "biothings_all"]


def get_predefined_api_set(api_set: str) -> dict:
    """Return the predefined API set for the given set name."""
    if api_set == "biothings_core":
        return {
            "smartapi_ids": [
                "59dce17363dce279d389100834e43648",  # MyGene.info
                "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
                "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
                "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
            ]
        }
    if api_set == "biothings_test":
        # biothings core APIs plus the SemmedDB API, useful for testings
        return {
            "smartapi_ids": [
                "59dce17363dce279d389100834e43648",  # MyGene.info
                "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
                "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
                "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
                "1d288b3a3caf75d541ffaae3aab386c8",  # SemmedDB
            ]
        }
    if api_set == "biothings_all":
        # include all biothings APIs with a few excluded
        return {
            "smartapi_q": (
                "_status.uptime_status:pass AND tags.name=biothings AND"
                " NOT tags.name=trapi"
            ),
            "smartapi_exclude_ids": [
                "1c9be9e56f93f54192dcac203f21c357",  # BioThings mabs API
                "5a4c41bf2076b469a0e9cfcf2f2b8f29",  # Translator Annotation Service
                "cc857d5b7c8b7609b5bbb38ff990bfff",  # GO Biological Process API
                "f339b28426e7bf72028f60feefcd7465",  # GO Cellular Component API
                "34bad236d77bea0a0ee6c6cba5be54a6",  # GO Molecular Function API
            ],
        }
    err_msg = f"Unknown API set: {api_set}"
    raise ValueError(err_msg)
