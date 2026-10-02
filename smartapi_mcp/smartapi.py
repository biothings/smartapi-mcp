"""
SmartAPI Registry Integration

Handles interaction with the SmartAPI registry.
"""

import logging
import re

import httpx2

from .openapi import fetch_spec

logger = logging.getLogger(__name__)

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


# "Production" as a word in a server description, case-insensitively, but not
# "non-production" / "Non-Production" / "non production".
_PRODUCTION_DESC_RE = re.compile(r"(?<![\w-])(?<!non )production\b", re.IGNORECASE)

# ``x-maturity`` values that positively declare a server is not production.
# Servers labelled this way are not used by the first-server fallback.
_NON_PRODUCTION_MATURITIES = {"development", "testing", "staging"}


def _maturity(server: dict) -> str:
    return str(server.get("x-maturity", "")).strip().lower()


def get_base_server_url(api_spec: dict) -> str:
    """Return the base server URL for the given API specification.

    With one server, that server is used. With several, the first match wins
    among, in order: a ``ci.transltr.io`` URL or a description naming it the
    production server; an ``x-maturity: production`` server; and finally the
    first listed absolute ``http(s)`` server not labelled as a non-production
    maturity, with a warning, since that is the default OpenAPI tooling uses.
    Raises :class:`ValueError` when there is nothing usable to pick.
    """
    title = (api_spec.get("info") or {}).get("title") or ""
    api_name = re.sub(r"[^a-z0-9_-]", "_", title.lower())
    servers = api_spec.get("servers")
    if not isinstance(servers, list) or not servers:
        # A missing ``servers`` key used to escape as an opaque KeyError.
        err_msg = (
            f"Cannot determine server URL for API: {api_name}\n"
            "The spec declares no servers."
        )
        raise ValueError(err_msg)
    servers = [server for server in servers if isinstance(server, dict)]

    base_server_url = None
    if len(servers) == 1:
        base_server_url = servers[0].get("url")
    elif len(servers) > 1:
        for server in servers:
            server_desc = server.get("description") or ""
            # ``url`` is required by OpenAPI but read defensively: a servers
            # entry without one used to raise KeyError here, which surfaced as
            # an opaque "KeyError: 'url'" instead of the clear ValueError below.
            server_url = server.get("url") or ""
            if "ci.transltr.io" in server_url.lower():
                base_server_url = server_url
                break
            if server_url and _PRODUCTION_DESC_RE.search(server_desc):
                base_server_url = server_url
                break
    if not base_server_url:
        # Fall back to the machine-readable ``x-maturity`` extension. The
        # heuristics above only inspect the free-text ``description``, but the
        # Translator APIs record maturity in this field instead -- so specs that
        # plainly declare a production server were being refused. Measured on
        # the registry's uptime-passing set, this recovers 7 of 14 failures
        # (Sri-node-normalizer, five Automat services, Metadata Domain).
        #
        # Checked *after* the existing rules rather than before them, so every
        # API that already resolves keeps resolving to the same URL; this only
        # rescues specs that would otherwise raise.
        for server in servers:
            if _maturity(server) == "production" and server.get("url"):
                base_server_url = server["url"]
                break
    if not base_server_url:
        # Last resort: the first listed server, which is the default OpenAPI
        # tooling (Swagger UI, generated clients) uses. Skipping the API instead
        # threw away specs like Identifiers.org's, which lists three mirrors of
        # one service and calls none of them "production". Relative URLs are
        # skipped -- OpenAPI resolves them against the spec's own location,
        # which for registry specs is smart-api.info -- and so are servers whose
        # ``x-maturity`` positively says they are not production: a spec that
        # declares only development and testing deployments (Aragorn) is
        # stating that no production instance exists.
        candidates = [
            server
            for server in servers
            if re.match(r"https?://", server.get("url") or "", re.IGNORECASE)
            and _maturity(server) not in _NON_PRODUCTION_MATURITIES
        ]
        if candidates:
            base_server_url = candidates[0]["url"]
            logger.warning(
                f"No production server identified for API '{title}'; using the "
                f"first listed server {base_server_url} (of {len(servers)})."
            )

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

PREDEFINED_API_SETS = ["biothings_core", "biothings_test", "biothings_all", "all"]

# Registry query selecting every API the SmartAPI registry currently reports as
# reachable. Used by the ``all`` preset.
WORKING_APIS_QUERY = "_status.uptime_status:pass"


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
    if api_set == "all":
        # Every API the registry reports as up, BioThings or not. Practical
        # because the defaults keep the listing small: the BioThings family
        # goes through the facade (~5 tools, no spec downloads) and the
        # remaining per-API tools are collapsed behind tool search. Measured on
        # ~106 APIs: 7 listed tools, ~1.9k tokens of tools/list, ~19s startup.
        # APIs whose specs cannot be loaded are skipped with a warning rather
        # than failing the whole server.
        return {"smartapi_q": WORKING_APIS_QUERY}
    err_msg = f"Unknown API set: {api_set}"
    raise ValueError(err_msg)
