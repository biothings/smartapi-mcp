"""Smart Router and Progressive Loader Functions."""

import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from awslabs.openapi_mcp_server import logger
from fastmcp import FastMCP
from fastmcp.tools import Tool

from .smartapi import load_api_spec

try:  # Optional semantic search dependencies
    import faiss  # type: ignore
    import numpy as np
    from sentence_transformers import SentenceTransformer

    SEMANTIC_SEARCH_AVAILABLE = True
except Exception:  # pragma: no cover - optional dependency path
    faiss = None  # type: ignore[assignment]
    np = None  # type: ignore[assignment]
    SentenceTransformer = None  # type: ignore[assignment]
    SEMANTIC_SEARCH_AVAILABLE = False


SEMANTIC_CACHE_DIR = Path.home() / ".smartapi_mcp"
SEMANTIC_INDEX_FILE = SEMANTIC_CACHE_DIR / "semantic_index.faiss"
API_DESCRIPTIONS_CACHE = SEMANTIC_CACHE_DIR / "api_descriptions.json"
API_IDS_CACHE = SEMANTIC_CACHE_DIR / "api_ids.json"
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

_semantic_cache: dict[str, Any] = {
    "index": None,
    "ids": None,
    "descriptions": None,
    "model": None,
}


def _ensure_cache_dir() -> None:
    SEMANTIC_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _load_cached_descriptions() -> tuple[list[str], dict[str, str]] | None:
    if not API_DESCRIPTIONS_CACHE.exists() or not API_IDS_CACHE.exists():
        return None
    try:
        ids = json.loads(API_IDS_CACHE.read_text(encoding="utf-8"))
        descriptions = json.loads(API_DESCRIPTIONS_CACHE.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    if not isinstance(ids, list) or not isinstance(descriptions, dict):
        return None
    return ids, descriptions


def _save_cached_descriptions(api_ids: list[str], descriptions: dict[str, str]) -> None:
    _ensure_cache_dir()
    API_IDS_CACHE.write_text(json.dumps(api_ids), encoding="utf-8")
    API_DESCRIPTIONS_CACHE.write_text(json.dumps(descriptions), encoding="utf-8")


def _load_cached_index() -> Any | None:
    if not SEMANTIC_SEARCH_AVAILABLE or not SEMANTIC_INDEX_FILE.exists():
        return None
    if faiss is None:
        return None
    try:
        return faiss.read_index(str(SEMANTIC_INDEX_FILE))
    except Exception:  # pragma: no cover - faiss read errors
        return None


def _save_cached_index(index: Any) -> None:
    if not SEMANTIC_SEARCH_AVAILABLE:
        return
    if faiss is None:
        return
    _ensure_cache_dir()
    faiss.write_index(index, str(SEMANTIC_INDEX_FILE))


def _load_model() -> Any:
    if SentenceTransformer is None:
        err_msg = "Semantic search dependencies unavailable."
        raise RuntimeError(err_msg)
    if _semantic_cache["model"] is None:
        _semantic_cache["model"] = SentenceTransformer(EMBEDDING_MODEL_NAME)
    return _semantic_cache["model"]


def _build_api_descriptions(smartapi_ids: list[str]) -> dict[str, str]:
    descriptions: dict[str, str] = {}
    for api_id in smartapi_ids:
        try:
            spec = load_api_spec(api_id)
        except Exception as exc:  # pragma: no cover - network/spec errors
            logger.warning(f"Failed to load API spec for {api_id}: {exc}")
            continue
        info = spec.get("info", {}) if isinstance(spec, dict) else {}
        title = info.get("title", "")
        summary = info.get("summary", "")
        description = info.get("description", "")
        combined = " ".join(part for part in [title, summary, description] if part)
        descriptions[api_id] = combined or api_id
    return descriptions


def _ensure_semantic_index(
    smartapi_ids: list[str],
) -> tuple[Any, list[str], dict[str, str]]:
    if not SEMANTIC_SEARCH_AVAILABLE or faiss is None or np is None:
        err_msg = "Semantic search dependencies unavailable."
        raise RuntimeError(err_msg)

    cached = _load_cached_descriptions()
    if cached:
        cached_ids, cached_descriptions = cached
        if cached_ids == smartapi_ids:
            cached_index = _load_cached_index()
            if cached_index is not None:
                _semantic_cache["index"] = cached_index
                _semantic_cache["ids"] = cached_ids
                _semantic_cache["descriptions"] = cached_descriptions
                return (
                    _semantic_cache["index"],
                    _semantic_cache["ids"],
                    _semantic_cache["descriptions"],
                )

    descriptions = _build_api_descriptions(smartapi_ids)
    ids = list(descriptions.keys())
    if not ids:
        err_msg = "No API descriptions available for semantic search."
        raise ValueError(err_msg)

    model = _load_model()
    embeddings = model.encode([descriptions[api_id] for api_id in ids])
    embeddings_np = np.array(embeddings, dtype="float32")

    index = faiss.IndexFlatIP(embeddings_np.shape[1])
    faiss.normalize_L2(embeddings_np)
    index.add(embeddings_np)  # type: ignore[call-arg]

    _semantic_cache["index"] = index
    _semantic_cache["ids"] = ids
    _semantic_cache["descriptions"] = descriptions
    _save_cached_descriptions(ids, descriptions)
    _save_cached_index(index)
    return (
        _semantic_cache["index"],
        _semantic_cache["ids"],
        _semantic_cache["descriptions"],
    )


def _category_routing(query: str, smartapi_ids: list[str]) -> dict[str, list[str]]:
    categories = {
        "bioinformatics": [
            "gene",
            "protein",
            "genomic",
            "genome",
            "sequence",
            "variant",
            "mutation",
            "pathway",
            "bio",
        ],
        "clinical": ["clinical", "patient", "phenotype", "disease", "trial"],
        "literature": ["literature", "publication", "paper", "abstract"],
    }
    query_lower = query.lower()
    matched_categories = [
        category
        for category, keywords in categories.items()
        if any(keyword in query_lower for keyword in keywords)
    ]
    if not matched_categories:
        return {}

    descriptions = _build_api_descriptions(smartapi_ids)
    results: dict[str, list[str]] = defaultdict(list)
    for api_id, text in descriptions.items():
        text_lower = text.lower()
        for category in matched_categories:
            if any(keyword in text_lower for keyword in categories[category]):
                results[category].append(api_id)
    return dict(results)


async def smart_search_smartapi(
    query: str, smartapi_ids: list[str], limit: int = 5
) -> dict[str, Any]:
    """Hybrid search over SmartAPI IDs using semantic or category routing."""
    if SEMANTIC_SEARCH_AVAILABLE:
        try:
            index, ids, descriptions = _ensure_semantic_index(smartapi_ids)
            model = _load_model()
            query_embedding = model.encode([query])
            if np is None or faiss is None:
                err_msg = "Semantic search dependencies unavailable."
                raise RuntimeError(err_msg)
            query_np = np.array(query_embedding, dtype="float32")
            faiss.normalize_L2(query_np)
            distances, indices = index.search(query_np, limit)

            results: dict[str, dict[str, Any]] = {}
            for score, idx in zip(distances[0], indices[0], strict=False):
                if idx < 0 or idx >= len(ids):
                    continue
                api_id = ids[idx]
                results[api_id] = {
                    "score": float(score),
                    "description": descriptions.get(api_id, ""),
                }
            if results:
                return {
                    "method": "semantic_search",
                    "results": results,
                    "total_found": len(results),
                }
        except Exception as exc:
            logger.warning(f"Semantic search failed, falling back: {exc}")

    category_results = _category_routing(query, smartapi_ids)
    return {
        "method": "category_routing",
        "results": category_results,
        "total_found": sum(len(ids) for ids in category_results.values()),
    }


async def debug_search_smartapi(
    query: str, smartapi_ids: list[str], limit: int = 5
) -> dict[str, Any]:
    result = await smart_search_smartapi(query, smartapi_ids, limit)
    method = result.get("method", "unknown")
    raw_results = result.get("results", {})
    debug_entries: list[dict[str, Any]] = []

    if method == "category_routing":
        for category, api_ids in raw_results.items():
            for api_id in api_ids[:limit]:
                title = ""
                try:
                    spec = load_api_spec(api_id)
                    title = spec.get("info", {}).get("title", "")
                except Exception as exc:  # pragma: no cover - network/spec errors
                    title = f"<failed to load spec: {exc}>"
                debug_entries.append(
                    {"id": api_id, "title": title, "category": category}
                )
        return {
            "method": method,
            "total_found": result.get("total_found", 0),
            "results": debug_entries,
        }

    for api_id, info in raw_results.items():
        title = ""
        try:
            spec = load_api_spec(api_id)
            title = spec.get("info", {}).get("title", "")
        except Exception as exc:  # pragma: no cover - network/spec errors
            title = f"<failed to load spec: {exc}>"
        entry = {
            "id": api_id,
            "title": title,
            "score": info.get("score"),
        }
        debug_entries.append(entry)
    return {
        "method": method,
        "total_found": result.get("total_found", 0),
        "results": debug_entries,
    }


async def create_smart_router_server(
    smartapi_ids: list[str], server_name: str, max_tools: int
) -> FastMCP:
    """Create server with smart routing capabilities."""
    router_server = FastMCP(f"{server_name}-router")

    async def smart_search(query: str, limit: int = 5) -> str:
        result = await smart_search_smartapi(query, smartapi_ids, limit)
        method = result.get("method", "unknown")
        results = result.get("results", {})
        if method == "category_routing":
            categories = list(results.keys())[:3]
            sample_ids = []
            for category in categories:
                sample_ids.extend(results.get(category, [])[:2])
            return (
                f"✅ Found {result['total_found']} APIs via category routing. "
                f"Categories: {categories}. Sample IDs: {sample_ids}"
            )
        api_ids = list(results.keys())[:3]
        return (
            f"🔍 Semantic search found {result['total_found']} relevant APIs: {api_ids}"
        )

    router_server.add_tool(
        Tool.from_function(
            smart_search,
            name="search_smartapi",
            description=(
                f"Intelligently search across {len(smartapi_ids)} SmartAPIs by "
                "category or semantic query. Use this first to discover relevant "
                "APIs before loading specific tools."
            ),
        )
    )

    async def load_tools_batch(api_ids: list[str]) -> str:
        """Load tools in batches to respect context limits."""
        from .server import merge_mcp_servers  # noqa: PLC0415

        batch_ids = api_ids[:max_tools]
        if not batch_ids:
            return "No API IDs provided to load."

        servers = []
        for api_id in batch_ids:
            try:
                server = await _load_single_server(api_id)
                servers.append(server)
            except Exception as exc:  # pragma: no cover - network/spec errors
                logger.warning(f"Failed to load SmartAPI {api_id}: {exc}")

        if not servers:
            return "No tools loaded."

        merged = await merge_mcp_servers(servers, f"{server_name}-batch")
        tools = await merged.get_tools()
        for tool in tools.values():
            router_server.add_tool(tool)
        return f"📦 Loaded {len(servers)} APIs with {len(tools)} tools."

    router_server.add_tool(
        Tool.from_function(
            load_tools_batch,
            name="load_tools_batch",
            description=(
                f"Load SmartAPI tools in batches of {max_tools} after search. "
                "Provide API IDs to load their tools."
            ),
        )
    )

    return router_server


async def create_progressive_server(
    smartapi_ids: list[str], server_name: str, max_tools: int
) -> FastMCP:
    """Create server with progressive loading."""
    progressive_server = FastMCP(f"{server_name}-progressive")

    async def load_tools_batch(api_ids: list[str]) -> str:
        """Load tools in batches to respect context limits."""
        from .server import merge_mcp_servers  # noqa: PLC0415

        batch_ids = api_ids[:max_tools] if api_ids else smartapi_ids[:max_tools]
        if not batch_ids:
            return "No API IDs provided to load."

        servers = []
        for api_id in batch_ids:
            try:
                server = await _load_single_server(api_id)
                servers.append(server)
            except Exception as exc:  # pragma: no cover - network/spec errors
                logger.warning(f"Failed to load SmartAPI {api_id}: {exc}")

        if not servers:
            return "No tools loaded."

        merged = await merge_mcp_servers(servers, f"{server_name}-batch")
        tools = await merged.get_tools()
        for tool in tools.values():
            progressive_server.add_tool(tool)
        return f"📦 Loaded {len(servers)} APIs with {len(tools)} tools."

    progressive_server.add_tool(
        Tool.from_function(
            load_tools_batch,
            name="load_tools_batch",
            description=(
                f"Load SmartAPI tools in batches of {max_tools} to manage context "
                "usage. Provide API IDs to load their tools."
            ),
        )
    )

    return progressive_server


async def _load_single_server(api_id: str) -> FastMCP:
    from .server import get_mcp_server  # noqa: PLC0415

    return await get_mcp_server(api_id)
