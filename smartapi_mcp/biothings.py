"""
BioThings generic-facade MCP server.

BioThings APIs all expose the same handful of operations (``/query``,
``/{type}/{id}``, batch ``POST /{type}``, ``/metadata/fields``). Rather than
emitting one MCP tool per (API x operation) -- which explodes to 200+ near
duplicate tools for ``biothings_all`` and overflows client context -- this
module exposes a small, fixed set of *generic* tools where the target API is a
parameter. The tool count stays constant (~5) no matter how many APIs are in
the set, so the server works on every MCP client without depending on runtime
``tools/list_changed`` notifications.
"""

import asyncio
import re
from dataclasses import dataclass, field

import httpx
from fastmcp import FastMCP
from fastmcp.tools import Tool

from .log import logger
from .smartapi import (
    HTTP_TIMEOUT,
    get_base_server_url,
    get_smartapi_registry,
    load_api_spec,
)

# Matches a BioThings annotation path like ``/gene/{geneid}`` and captures the
# entity (biothing) type segment.
_BIOTHING_PATH_RE = re.compile(r"^/(?P<type>[^/{}]+)/\{[^/]+\}$")

# Truncate API descriptions in discovery output to keep the payload small.
_MAX_DESC_LEN = 200

# HTTP methods recognized when enumerating spec operations.
_HTTP_METHODS = {"get", "post", "put", "delete", "patch", "head", "options"}


@dataclass
class BioThingsAPIEntry:
    """A single BioThings API in the facade registry."""

    name: str  # short slug used as the ``api`` argument value, e.g. "mygene"
    smartapi_id: str
    title: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    # Resolved lazily on first use (one spec download per API):
    base_url: str | None = None
    biothing_type: str | None = None


def _slugify_title(title: str) -> str:
    """Turn an API title into a short slug, e.g. 'MyGene.info API' -> 'mygene'."""
    slug = title.lower()
    slug = re.sub(r"\.info\b", "", slug)
    slug = re.sub(r"\bapi\b", "", slug)
    slug = re.sub(r"[^a-z0-9]+", "_", slug).strip("_")
    return slug or "api"


def build_registry_from_entries(entries: list[dict]) -> dict[str, BioThingsAPIEntry]:
    """Build a slug -> entry registry from raw SmartAPI registry records.

    Slugs are derived from API titles and de-duplicated with numeric suffixes.
    """
    registry: dict[str, BioThingsAPIEntry] = {}
    for record in entries:
        smartapi_id = record.get("_id", "")
        if not smartapi_id:
            continue
        title = record.get("title", "") or smartapi_id
        base_slug = _slugify_title(title)
        slug = base_slug
        suffix = 2
        while slug in registry:
            slug = f"{base_slug}_{suffix}"
            suffix += 1
        registry[slug] = BioThingsAPIEntry(
            name=slug,
            smartapi_id=smartapi_id,
            title=title,
            description=record.get("description", "") or "",
            tags=list(record.get("tags", []) or []),
        )
    return registry


async def build_registry(
    smartapi_ids: list[str] | None = None, *, q: str | None = None
) -> dict[str, BioThingsAPIEntry]:
    """Build the facade registry from a set of IDs (or a registry query)."""
    entries = await get_smartapi_registry(q=q, ids=smartapi_ids)
    return build_registry_from_entries(entries)


def is_biothings_registry(registry: dict[str, BioThingsAPIEntry]) -> bool:
    """True only if every API in the registry is tagged ``biothings``."""
    if not registry:
        return False
    return all("biothings" in entry.tags for entry in registry.values())


def _resolve_endpoints(entry: BioThingsAPIEntry) -> None:
    """Lazily resolve and cache ``base_url`` and ``biothing_type`` from the spec."""
    if entry.base_url is not None and entry.biothing_type is not None:
        return
    spec = load_api_spec(entry.smartapi_id)
    if entry.base_url is None:
        entry.base_url = get_base_server_url(spec).rstrip("/")
    if entry.biothing_type is None:
        for path in spec.get("paths", {}):
            match = _BIOTHING_PATH_RE.match(path)
            if match:
                entry.biothing_type = match.group("type")
                break


def _normalize_path(path: str) -> str:
    """Replace any ``{param}`` segment with ``{}`` so paths compare structurally."""
    return re.sub(r"\{[^/}]+\}", "{}", path)


def _spec_operations(spec: dict) -> set[tuple[str, str]]:
    """Return the set of ``(METHOD, normalized_path)`` operations in a spec."""
    ops: set[tuple[str, str]] = set()
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        norm = _normalize_path(path)
        for method in item:
            if method.lower() in _HTTP_METHODS:
                ops.add((method.upper(), norm))
    return ops


def _standard_biothings_ops(biothing_type: str) -> set[tuple[str, str]]:
    """The operations a stock BioThings API exposes for a given entity type."""
    return {
        ("GET", "/query"),
        ("POST", "/query"),
        ("GET", f"/{biothing_type}/{{}}"),
        ("POST", f"/{biothing_type}"),
        ("GET", "/metadata"),
        ("GET", "/metadata/fields"),
    }


def analyze_biothings_spec(
    spec: dict,
) -> tuple[str | None, str | None, list[tuple[str, str]]]:
    """Classify a BioThings spec for facade eligibility.

    Returns ``(base_url, biothing_type, extra_ops)`` where ``extra_ops`` lists
    operations that fall outside the standard BioThings interface. An empty
    ``extra_ops`` (with a detected ``biothing_type``) means the API is fully
    covered by the generic facade tools; otherwise it should be served with
    faithful per-API tools so the extra endpoints aren't hidden.
    """
    try:
        base_url = get_base_server_url(spec).rstrip("/")
    except (KeyError, ValueError, TypeError):
        base_url = None

    biothing_type = None
    for path in spec.get("paths", {}):
        match = _BIOTHING_PATH_RE.match(path)
        if match:
            biothing_type = match.group("type")
            break

    ops = _spec_operations(spec)
    if biothing_type is None:
        extra = sorted(ops)
    else:
        extra = sorted(ops - _standard_biothings_ops(biothing_type))
    return base_url, biothing_type, extra


async def partition_biothings(
    entries: dict[str, BioThingsAPIEntry],
) -> tuple[dict[str, BioThingsAPIEntry], list[str]]:
    """Split BioThings entries into facade-eligible vs. needs-per-API.

    Loads each spec (in parallel) and classifies it with
    :func:`analyze_biothings_spec`. Facade-eligible entries get their
    ``base_url``/``biothing_type`` cached and are returned in the first dict;
    APIs with extra endpoints, no detectable entity type, or an unloadable spec
    are returned as a list of SmartAPI IDs to be served with per-API tools.
    """
    items = list(entries.items())
    specs = await asyncio.gather(
        *[asyncio.to_thread(load_api_spec, entry.smartapi_id) for _, entry in items],
        return_exceptions=True,
    )

    facade_entries: dict[str, BioThingsAPIEntry] = {}
    extra_ids: list[str] = []
    for (name, entry), spec in zip(items, specs, strict=True):
        if isinstance(spec, Exception):
            logger.warning(
                f"Could not load spec for BioThings API '{name}' "
                f"({entry.smartapi_id}): {spec}; serving with per-API tools."
            )
            extra_ids.append(entry.smartapi_id)
            continue
        base_url, biothing_type, extra_ops = analyze_biothings_spec(spec)
        if biothing_type is None or extra_ops:
            reason = (
                f"non-standard endpoint(s) {extra_ops}"
                if extra_ops
                else "no detectable entity type"
            )
            logger.info(
                f"BioThings API '{name}' has {reason}; "
                "serving it with faithful per-API tools."
            )
            extra_ids.append(entry.smartapi_id)
        else:
            entry.base_url = base_url
            entry.biothing_type = biothing_type
            facade_entries[name] = entry
    return facade_entries, extra_ids


def _score_entry(entry: BioThingsAPIEntry, tokens: list[str]) -> int:
    """Lexical relevance: count token hits across title/description/tags."""
    haystack = " ".join(
        [entry.name, entry.title, entry.description, " ".join(entry.tags)]
    ).lower()
    return sum(haystack.count(token) for token in tokens)


def rank_apis(
    registry: dict[str, BioThingsAPIEntry],
    keyword: str | None = None,
    limit: int = 10,
) -> list[dict]:
    """Rank APIs by lexical relevance to ``keyword`` (returns plain data).

    With no keyword, returns the full catalog sorted by name. Descriptions are
    truncated to keep the payload small.
    """

    def _as_dict(entry: BioThingsAPIEntry) -> dict:
        desc = entry.description
        if len(desc) > _MAX_DESC_LEN:
            desc = desc[:_MAX_DESC_LEN].rstrip() + "..."
        return {
            "name": entry.name,
            "title": entry.title,
            "description": desc,
            "tags": entry.tags,
        }

    if not keyword or not keyword.strip():
        return [_as_dict(registry[name]) for name in sorted(registry)]

    tokens = [tok for tok in re.split(r"\W+", keyword.lower()) if tok]
    scored = [(_score_entry(entry, tokens), entry) for entry in registry.values()]
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    return [{**_as_dict(entry), "score": score} for score, entry in scored[:limit]]


def build_biothings_facade(
    registry: dict[str, BioThingsAPIEntry], server_name: str = "smartapi_mcp"
) -> FastMCP:
    """Build a FastMCP server exposing generic BioThings tools over ``registry``."""
    server = FastMCP(server_name)
    valid_names = ", ".join(sorted(registry))
    api_help = (
        "BioThings API to target, given as its short name. "
        "Call list_biothings_apis to discover APIs. "
        f"Available: {valid_names}"
    )

    def _entry(api: str) -> BioThingsAPIEntry:
        entry = registry.get(api)
        if entry is None:
            err_msg = (
                f"Unknown api {api!r}. Valid values: {valid_names}. "
                "Use list_biothings_apis to discover available APIs."
            )
            raise ValueError(err_msg)
        _resolve_endpoints(entry)
        return entry

    async def _request(method: str, url: str, **kwargs) -> dict | list:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.request(method, url, **kwargs)
            response.raise_for_status()
            return response.json()

    async def list_biothings_apis(
        keyword: str | None = None, limit: int = 10
    ) -> list[dict]:
        """List/search the available BioThings APIs and return matching records."""
        return rank_apis(registry, keyword, limit)

    async def biothings_query(
        api: str,
        q: str,
        fields: str = "all",
        size: int = 10,
        from_: int = 0,
    ) -> dict | list:
        """Search a BioThings API (GET /query)."""
        entry = _entry(api)
        params = {"q": q, "fields": fields, "size": size, "from": from_}
        return await _request("GET", f"{entry.base_url}/query", params=params)

    async def biothings_get(
        api: str,
        id: str,  # noqa: A002 - `id` is the natural BioThings parameter name
        fields: str = "all",
    ) -> dict | list:
        """Retrieve a single annotation by id (GET /{type}/{id})."""
        entry = _entry(api)
        if not entry.biothing_type:
            err_msg = f"Could not determine the entity type for api {api!r}."
            raise ValueError(err_msg)
        url = f"{entry.base_url}/{entry.biothing_type}/{id}"
        return await _request("GET", url, params={"fields": fields})

    async def biothings_getbatch(
        api: str,
        ids: list[str],
        fields: str = "all",
        scopes: str | None = None,
    ) -> dict | list:
        """Retrieve annotations for multiple ids (POST /{type})."""
        entry = _entry(api)
        if not entry.biothing_type:
            err_msg = f"Could not determine the entity type for api {api!r}."
            raise ValueError(err_msg)
        data = {"ids": ",".join(ids), "fields": fields}
        if scopes:
            data["scopes"] = scopes
        url = f"{entry.base_url}/{entry.biothing_type}"
        return await _request("POST", url, data=data)

    async def biothings_fields(api: str) -> dict | list:
        """List the queryable/returnable fields for a BioThings API."""
        entry = _entry(api)
        return await _request("GET", f"{entry.base_url}/metadata/fields")

    server.add_tool(
        Tool.from_function(
            list_biothings_apis,
            name="list_biothings_apis",
            description=(
                f"Discover which of the {len(registry)} available BioThings APIs "
                "to use. Optionally pass a keyword to rank by relevance. Returns "
                "API names, titles, descriptions and tags. Call this first, then "
                "pass a returned name as the `api` argument to the other tools."
            ),
        )
    )
    biothings_query.__doc__ = (
        "Search a BioThings API. `api` is the API name (see list_biothings_apis); "
        "`q` is a query string (e.g. 'symbol:CDK2' or 'diabetes')."
    )
    for func, name in (
        (biothings_query, "biothings_query"),
        (biothings_get, "biothings_get"),
        (biothings_getbatch, "biothings_getbatch"),
        (biothings_fields, "biothings_fields"),
    ):
        tool = Tool.from_function(func, name=name)
        # Surface the list of valid `api` values in the tool description.
        tool.description = f"{(func.__doc__ or '').strip()}\n\n{api_help}"
        server.add_tool(tool)

    logger.info(
        f"Built BioThings facade '{server_name}' with {len(registry)} "
        "APIs as 5 generic tools."
    )
    return server
