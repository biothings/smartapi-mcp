"""
SmartAPI Registry Integration

Handles interaction with the SmartAPI registry.
"""

import re

import httpx2

from .openapi import fetch_spec

smartapi_query_url = "https://smart-api.info/api/query"
smartapi_spec_url = "https://smart-api.info/api/metadata/{smartapi_id}"

# Default timeout (seconds) for all SmartAPI registry HTTP calls.
HTTP_TIMEOUT = 30.0


async def get_smartapi_registry(
    q: str | None = None, ids: list[str] | None = None
) -> list[dict]:
    """Query the SmartAPI registry and return metadata for matching APIs.

    Returns a list of ``{"_id", "title", "description", "tags"}`` dicts. Pass
    either a query string ``q`` or an explicit list of ``ids`` (which is turned
    into an ``_id:(...)`` query so a whole set is fetched in a single request).
    """
    if ids:
        q = "_id:({})".format(" OR ".join(ids))
    if not q:
        err_msg = "Either a query string or a list of IDs must be provided."
        raise ValueError(err_msg)

    params = {
        "q": q,
        "fields": "info.title,info.description,tags",
        "size": 500,
        "raw": 1,
    }
    async with httpx2.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        response = await client.get(smartapi_query_url, params=params)
        response.raise_for_status()
        data = response.json()

    entries: list[dict] = []
    for hit in data.get("hits", []):
        info = hit.get("info", {}) or {}
        tags = [
            tag.get("name", "") for tag in hit.get("tags", []) if isinstance(tag, dict)
        ]
        entries.append(
            {
                "_id": hit.get("_id", ""),
                "title": info.get("title", ""),
                "description": info.get("description", ""),
                "tags": [tag for tag in tags if tag],
            }
        )
    return entries


async def get_smartapi_ids(q: str) -> list[str]:
    """Give a query string, return a list of SmartAPI IDs matching the query."""
    entries = await get_smartapi_registry(q=q)
    return [entry["_id"] for entry in entries if entry["_id"]]


def load_api_spec(smartapi_id: str) -> dict:
    """Fetch and validate the OpenAPI spec registered under ``smartapi_id``.

    Raises :class:`~smartapi_mcp.openapi.SpecError` (a ``ValueError``) if the
    spec is unusable, so callers building many APIs can skip just that one.
    Results are cached, which matters on the ``--facade-strict`` path where a
    spec is inspected and then built from.
    """
    return fetch_spec(smartapi_spec_url.format(smartapi_id=smartapi_id))


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


# The core BioThings APIs: the canonical, broad-coverage annotation services,
# as distinct from the ~50 single-source satellite APIs. Named because it serves
# two purposes that must not drift apart -- the ``biothings_core`` preset (which
# APIs to serve) and discovery ranking (which APIs to prefer when several match
# a query, see ``CORE_API_BOOST`` in :mod:`smartapi_mcp.biothings`).
CORE_BIOTHINGS_API_IDS = [
    "59dce17363dce279d389100834e43648",  # MyGene.info
    "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
    "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
    "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
    "85139f4dccfcefa3ac3042372066916d",  # MyGeneSet.info
    "f7943e6167166b3ea9e4b8be08f45fa6",  # MyTaxon.info
]

# SemmedDB, added to the "test" set for its non-standard /query/ngd endpoint.
_SEMMEDDB_ID = "1d288b3a3caf75d541ffaae3aab386c8"

PREDEFINED_API_SETS = ["biothings_core", "biothings_test", "biothings_all"]


def get_predefined_api_set(api_set: str) -> dict:
    """Return the predefined API set for the given set name."""
    if api_set == "biothings_core":
        return {"smartapi_ids": list(CORE_BIOTHINGS_API_IDS)}
    if api_set == "biothings_test":
        # The core APIs plus SemmedDB, whose /query/ngd endpoint exercises the
        # non-standard-endpoint handling.
        return {"smartapi_ids": [*CORE_BIOTHINGS_API_IDS, _SEMMEDDB_ID]}
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
                "27a5b60716c3a401f2c021a5b718c5b1",  # SmartAPI registry API
            ],
        }
    err_msg = f"Unknown API set: {api_set}"
    raise ValueError(err_msg)
