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
import math
import re
from dataclasses import dataclass, field

import httpx
from awslabs.openapi_mcp_server import logger
from fastmcp import FastMCP
from fastmcp.tools import Tool

from .smartapi import (
    CORE_BIOTHINGS_API_IDS,
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

# Tags that disqualify an API from the BioThings *annotation-API family* even
# though it carries the "biothings" tag. TRAPI services (BioThings Explorer,
# Service Provider) are built by the same team and tagged accordingly, but they
# speak the Translator Reasoner API -- a query-graph protocol -- not the
# BioThings annotation interface, so none of the generic facade tools apply to
# them. They are served with faithful per-API tools instead.
#
# This is not a cosmetic distinction: the facade infers an entity type from the
# first ``/{type}/{id}``-shaped path, and BTE's ``GET /asyncquery_status/{id}``
# matches that shape. Without this exclusion, ``biothings_get`` would request
# ``/asyncquery_status/<id>`` and return a job status as though it were an
# annotation record -- a wrong answer with no error.
NON_FAMILY_TAGS = frozenset({"trapi"})


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


def is_biothings_family(entry: BioThingsAPIEntry) -> bool:
    """Whether ``entry`` is a BioThings annotation API the facade can serve.

    Requires the ``biothings`` tag and the absence of any
    :data:`NON_FAMILY_TAGS`.
    """
    tags = {str(tag).strip().lower() for tag in entry.tags}
    return "biothings" in tags and not (tags & NON_FAMILY_TAGS)


def is_biothings_registry(registry: dict[str, BioThingsAPIEntry]) -> bool:
    """True only if every API in the registry is a facade-servable BioThings API."""
    if not registry:
        return False
    return all(is_biothings_family(entry) for entry in registry.values())


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


# Words too common to discriminate between APIs. Without this, a natural-language
# intent like "get a gene annotation by its Entrez gene id" is dominated by
# "get"/"a"/"by"/"its"/"id" rather than by "gene" and "entrez".
_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "are",
        "as",
        "at",
        "be",
        "by",
        "for",
        "from",
        "get",
        "how",
        "in",
        "into",
        "is",
        "it",
        "its",
        "of",
        "on",
        "or",
        "that",
        "the",
        "their",
        "them",
        "there",
        "these",
        "this",
        "to",
        "what",
        "when",
        "where",
        "which",
        "who",
        "with",
        "api",
        "apis",
        "data",
        "database",
        "dataset",
        "info",
        "information",
        "record",
        "records",
        "service",
        "services",
    }
)


def _tokenize(text: str) -> list[str]:
    """Lower-case word tokens. Word-based, not substring-based, on purpose.

    The previous scorer used ``str.count`` on the raw text, so a query term
    like "id" also matched inside "identifier", "candidate" and "provide".
    """
    return re.findall(r"[a-z0-9]+", text.lower())


# How much more a term in the API's name/title counts than one buried in its
# description. An API *named* for a concept is a far stronger answer to a query
# about that concept than one merely mentioning it in prose; without this,
# scores tie constantly and the tie-break (alphabetical) decides, which
# systematically favours the "biothings_*"-prefixed names over MyGene/MyChem.
_NAME_FIELD_WEIGHT = 3.0

# Score multiplier for the core BioThings APIs (:data:`CORE_BIOTHINGS_API_IDS`).
#
# These are the canonical broad-coverage services, and they are the *worst*
# served by pure lexical scoring: being general means their descriptions carry
# the least distinctive vocabulary, while single-source satellite APIs read as
# highly specific. So a lexical ranker systematically under-ranks exactly the
# APIs a user most often wants, and needs a prior to correct for it.
#
# Measured on 20 BioThings intents. With the registry descriptions as they were
# before the core-API enrichment, no boost gave recall@5 16/20 (MRR 0.71) and
# only 3 of the 6 core-API intents were answered; 1.2 gives 19/20 (MRR 0.82).
# With the enriched descriptions live, no boost already gives 19/20 (MRR 0.92)
# and 1.2 gives 20/20 (MRR 0.90). Larger values buy nothing on recall and cost
# ranking quality once the metadata is good -- at 3.0 the post-enrichment MRR
# falls to 0.81 -- so this is deliberately the smallest value that captures the
# benefit, and it stays close to neutral as the metadata improves.
CORE_API_BOOST = 1.2

_CORE_API_IDS = frozenset(CORE_BIOTHINGS_API_IDS)


def _entry_terms(entry: BioThingsAPIEntry) -> tuple[set[str], set[str]]:
    """Return ``(name_terms, all_terms)`` for one API.

    ``name_terms`` covers the short name, title and tags -- the curated labels;
    ``all_terms`` adds the free-text description.
    """
    name_terms = set(
        _tokenize(" ".join([entry.name, entry.title, " ".join(map(str, entry.tags))]))
    )
    return name_terms, name_terms | set(_tokenize(entry.description))


def _score_entry(
    terms: tuple[set[str], set[str]],
    query_terms: list[str],
    idf: dict[str, float],
) -> float:
    """Score one API against a query. Higher is more relevant.

    ``terms`` is the ``(name_terms, all_terms)`` pair from :func:`_entry_terms`.

    Three deliberate properties:

    * **Binary term frequency.** A term counts once however often it appears, so
      an API with a long, repetitive description no longer outranks a precisely
      matching one. This was the concrete defect in the previous scorer:
      searching "get a gene annotation by its Entrez gene id" ranked MyGeneSet
      above MyGene, because summed substring counts reward verbosity.
    * **IDF weighting.** A term shared by most APIs ("gene", "translator")
      contributes almost nothing, while a rare one ("entrez", "ngd", "taxonomy")
      dominates -- which is what makes an intent select the API it names.
    * **Field weighting.** A hit in the name/title/tags counts
      :data:`_NAME_FIELD_WEIGHT` times one that is only in the description. An
      API *named* for a concept answers a query about it far better than one
      merely mentioning it in prose, and without this, scores tie constantly and
      the alphabetical tie-break decides -- which systematically favoured the
      ``biothings_*``-prefixed names over MyGene/MyChem/MyVariant.
    """
    name_terms, all_terms = terms
    score = 0.0
    for term in query_terms:
        weight = idf.get(term, 0.0)
        if not weight:
            continue
        if term in name_terms:
            score += weight * _NAME_FIELD_WEIGHT
        elif term in all_terms:
            score += weight
    return score


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

    query_terms = [t for t in _tokenize(keyword) if t not in _STOPWORDS]
    if not query_terms:
        # Nothing discriminating left (e.g. "what data is there?"): fall back to
        # the full catalog rather than returning an arbitrary subset.
        return [_as_dict(registry[name]) for name in sorted(registry)]

    terms_by_name = {name: _entry_terms(entry) for name, entry in registry.items()}
    total = len(registry)
    idf = {}
    for term in set(query_terms):
        seen_in = sum(1 for _, all_terms in terms_by_name.values() if term in all_terms)
        # Robertson/Sparck-Jones IDF. Chosen over the plain log(N/n) form
        # because it stays strictly positive even for a term present in every
        # API: with a small registry (say two APIs that both mention "gene"),
        # a zero weight would drop every candidate and the search would answer
        # "nothing found" for a query that in fact matches everything.
        idf[term] = math.log(1 + (total - seen_in + 0.5) / (seen_in + 0.5))

    scored = []
    for name, entry in registry.items():
        score = _score_entry(terms_by_name[name], query_terms, idf)
        if entry.smartapi_id in _CORE_API_IDS:
            # Multiplicative, not additive: a zero score stays zero, so the
            # boost reorders results that already match and never promotes a
            # core API into a query it has nothing to do with.
            score *= CORE_API_BOOST
        scored.append((score, entry))
    scored = [pair for pair in scored if pair[0] > 0]
    scored.sort(key=lambda pair: (-pair[0], pair[1].name))
    return [
        {**_as_dict(entry), "score": round(score, 3)} for score, entry in scored[:limit]
    ]


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
