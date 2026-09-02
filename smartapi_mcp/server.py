"""
SmartAPI MCP Server

Main MCP server implementation for SmartAPI integration.
"""

import hashlib
import re
from collections.abc import Iterable

from fastmcp import FastMCP
from fastmcp.server.transforms.search import (
    BM25SearchTransform,
    RegexSearchTransform,
    serialize_tools_for_output_markdown,
)

# Import BioThings generic-facade builder
from .biothings import (
    build_biothings_facade,
    build_registry,
    is_biothings_family,
    partition_biothings,
)
from .log import logger
from .openapi import build_openapi_server

# Import from smartapi module - avoiding circular imports
from .smartapi import (
    get_base_server_url,
    get_predefined_api_set,
    get_smartapi_ids,
    load_api_spec,
)

# Cap names at 64 characters. The MCP spec (SEP-986) recommends 1-64 chars for
# *tool* names as a SHOULD, but the limit is enforced as a hard error by the
# model APIs: both Anthropic (FrontendRemoteMcpToolDefinition.name; 400 on
# longer names) and OpenAI (^[a-zA-Z0-9_-]{1,64}$) reject names over 64 chars.
# So prefixed per-API names must be truncated to fit. The spec does not define a
# length for *prompt* names, but we cap them too as a harmless safeguard against
# clients that reuse the tool-name validator.
MAX_TOOL_NAME_LEN = 64

# Ways to expose a large tool catalog. "off" lists every tool; "bm25"/"regex"
# always replace the catalog with a search interface; "auto" picks between them
# by tool count (see :func:`apply_tool_search`).
TOOL_SEARCH_MODES = ("auto", "off", "bm25", "regex")

# Mode "auto" resolves to. BM25 handles natural-language queries; regex needs the
# caller to author a pattern and returns nothing (silently) if handed prose.
TOOL_SEARCH_AUTO_MODE = "bm25"

# Tool count at which "auto" turns search on.
#
# Measured over the registry's uptime-passing set (592 tools, 92 APIs), a single
# entry in `tools/list` -- name plus the enriched description plus the JSON input
# schema -- averages ~3,900 characters (~975 tokens), median ~1,270 (~320), p90
# ~7,500, with one TRAPI tool at 84,000 (~21,000 tokens). At this threshold a
# listing therefore costs roughly 5k tokens of median-sized tools or 15k of
# mean-sized ones, which is a reasonable ceiling to pay before search is worth
# its extra round trip.
#
# Note the 65x spread: tool *count* is a crude proxy for the thing we actually
# care about, which is payload size. A byte/token budget would be the better
# instrument and would make this constant a floor rather than the decision.
TOOL_SEARCH_AUTO_THRESHOLD = 15


async def apply_tool_search(
    server: FastMCP,
    mode: str = "off",
    *,
    max_results: int = 10,
    always_visible: Iterable[str] = (),
    threshold: int = TOOL_SEARCH_AUTO_THRESHOLD,
) -> FastMCP:
    """Collapse ``server``'s tool catalog behind a search interface.

    Serving many APIs from one server makes the tool list long enough to crowd
    out a client's context: the ``biothings_all`` set is ~50 APIs at ~6 tools
    each. A search transform replaces the listed catalog with two synthetic
    tools -- ``search_tools`` and ``call_tool`` -- so a model discovers tools on
    demand instead of receiving every schema upfront. Every real tool remains
    callable through ``call_tool``; only the *listing* changes.

    Names in ``always_visible`` stay listed alongside the synthetic tools.
    :func:`build_server_for_set` pins the BioThings facade tools this way, so
    the common path stays directly callable and only the per-API long tail is
    collapsed. That combination is the intended arrangement: the facade answers
    BioThings queries directly (where lexical search is weakest, because the
    generated per-API descriptions are near-identical boilerplate), and search
    covers the non-BioThings tail (where it works well).

    ``mode`` is one of :data:`TOOL_SEARCH_MODES`:

    ``"auto"``
        Enable :data:`TOOL_SEARCH_AUTO_MODE` once the server has at least
        ``threshold`` tools; leave smaller catalogs listed in full.
    ``"off"``
        Leave the catalog alone.
    ``"bm25"`` / ``"regex"``
        Always enable that transform, regardless of size.

    ``max_results`` caps the hits per search. ``server`` is mutated in place and
    returned.
    """
    if mode not in TOOL_SEARCH_MODES:
        err_msg = (
            f"Unknown tool search mode {mode!r}; "
            f"expected one of: {', '.join(TOOL_SEARCH_MODES)}."
        )
        raise ValueError(err_msg)
    if mode == "off":
        return server

    tool_count = len(await server.list_tools())
    if not tool_count:
        # Leave an empty server alone so the caller's "no tools registered"
        # diagnostics still fire instead of counting the synthetic tools.
        logger.warning(
            f"Tool search ({mode}) requested but the server has no tools; "
            "leaving the catalog unchanged."
        )
        return server

    if mode == "auto":
        if tool_count < threshold:
            logger.info(
                f"Tool search (auto): {tool_count} tools is below the "
                f"{threshold}-tool threshold; listing them all."
            )
            return server
        logger.info(
            f"Tool search (auto): {tool_count} tools reaches the "
            f"{threshold}-tool threshold; enabling {TOOL_SEARCH_AUTO_MODE}."
        )
        mode = TOOL_SEARCH_AUTO_MODE

    pinned = sorted(always_visible)
    transform_cls = BM25SearchTransform if mode == "bm25" else RegexSearchTransform
    server.add_transform(
        transform_cls(
            max_results=max_results,
            always_visible=pinned,
            # Markdown results are roughly half the size of the default JSON
            # serialization, which is the point when enabling search at all.
            search_result_serializer=serialize_tools_for_output_markdown,
        )
    )
    exposed = len(await server.list_tools())
    logger.info(
        f"Tool search ({mode}) enabled: {tool_count} tools collapsed to "
        f"{exposed} listed ({len(pinned)} pinned + search_tools/call_tool); "
        f"max_results={max_results}. All {tool_count} tools stay callable "
        "via call_tool."
    )
    return server


async def get_mcp_server(smartapi_id: str) -> FastMCP:
    """Build a faithful per-API MCP server for one SmartAPI id.

    The server is named after the spec's ``info.title``, which
    :func:`_merge_servers_into` turns into the per-API tool-name prefix.
    """
    openapi_spec = load_api_spec(smartapi_id)
    base_server_url = get_base_server_url(openapi_spec)
    api_name = (openapi_spec.get("info") or {}).get("title") or "OpenAPI MCP Server"

    return build_openapi_server(openapi_spec, base_server_url, api_name)


def _fit_name(name: str, used: set[str]) -> str:
    """Return a unique name no longer than :data:`MAX_TOOL_NAME_LEN` chars.

    Used for both tool and prompt names. Names within the limit (and not already
    in ``used``) are returned unchanged. Longer or colliding names are truncated
    and given a short hash suffix derived from the *full* name, so the result
    stays deterministic and collision-free (two different long names hash
    differently).
    """
    if len(name) <= MAX_TOOL_NAME_LEN and name not in used:
        return name

    digest = hashlib.sha1(name.encode()).hexdigest()[:6]  # noqa: S324 - non-crypto
    suffix = f"_{digest}"
    truncated = name[: MAX_TOOL_NAME_LEN - len(suffix)].rstrip("_") + suffix
    # Guard against the (unlikely) case where the truncated form still collides.
    while truncated in used:
        digest = hashlib.sha1((name + digest).encode()).hexdigest()[:6]  # noqa: S324
        suffix = f"_{digest}"
        truncated = name[: MAX_TOOL_NAME_LEN - len(suffix)].rstrip("_") + suffix
    logger.debug(
        f"Name '{name}' exceeds {MAX_TOOL_NAME_LEN} chars or collides; "
        f"renamed to '{truncated}'."
    )
    return truncated


async def build_api_servers(
    smartapi_ids: list[str],
) -> tuple[list[FastMCP], list[tuple[str, str]]]:
    """Build one MCP server per SmartAPI id, skipping the ones that fail.

    Returns ``(servers, failures)`` where each failure is ``(smartapi_id,
    reason)``.

    Not every registered spec can be turned into a server: some use external
    ``$ref``s (refused as an SSRF guard, see
    :func:`~smartapi_mcp.openapi.reject_external_refs`), some are invalid
    OpenAPI, some have no ``servers`` block. Roughly one in six of the
    registry's uptime-passing APIs fails for one of those reasons, and a single
    one of them used to abort the whole build -- so ``--smartapi_q
    '_status.uptime_status:pass'`` could not start at all. Serving the APIs that
    do work, and reporting the rest, is far more useful than serving none.

    Kept sequential like the code it replaces: fanning these out concurrently
    makes the SmartAPI registry start refusing DNS/connections partway through,
    which turns working APIs into spurious failures.
    """
    servers: list[FastMCP] = []
    failures: list[tuple[str, str]] = []
    for sid in smartapi_ids:
        try:
            servers.append(await get_mcp_server(sid))
        # SystemExit is caught alongside Exception on purpose, as a guard
        # against a dependency reporting an error by exiting the process rather
        # than raising. The awslabs wrapper this package used through 0.4.0 did
        # exactly that -- every spec error became sys.exit(1) from inside the
        # library, which "except Exception" does not catch, so one spec that
        # fastmcp rejected took down every other API in the set (it killed a
        # 27-API build at API 17 against the registry's uptime-passing set).
        # Nothing on this path does that any more, but the guard is a cheap
        # invariant: no single API may abort the whole build. It is scoped to
        # one call, so it cannot swallow a genuine interpreter exit, and Ctrl-C
        # raises KeyboardInterrupt rather than SystemExit.
        except (Exception, SystemExit) as exc:  # any spec problem is survivable
            reason = f"{type(exc).__name__}: {str(exc)[:200]}"
            failures.append((sid, reason))
            logger.warning(f"Skipping SmartAPI {sid}: {reason}")
    if failures:
        logger.warning(
            f"{len(failures)} of {len(smartapi_ids)} API(s) could not be loaded "
            f"and were skipped; {len(servers)} loaded successfully."
        )
    return servers, failures


async def _merge_servers_into(
    target: FastMCP, list_of_servers: list[FastMCP]
) -> FastMCP:
    """Add the tools/prompts of each server to ``target``, prefixed by API name.

    Tool and prompt names are prefixed with the source server's (API) name to
    avoid conflicts. ``target`` is mutated in place and returned.
    """
    # Seed with names already in the target (e.g. facade tools in the hybrid
    # path) so merged per-API tools/prompts never collide with them. Tools and
    # prompts have separate namespaces, so each gets its own set.
    used_tool_names: set[str] = {tool.name for tool in await target.list_tools()}
    used_prompt_names: set[str] = {
        prompt.name for prompt in await target.list_prompts()
    }
    for server in list_of_servers:
        api_name = re.sub(
            r"[^a-z0-9_-]", "_", getattr(server, "name", "unknown_api").lower()
        )

        tools = await server.list_tools()
        if tools:
            for tool in tools:
                # Rename the tool by prefixing with API name, keeping it within
                # the 64-char limit that MCP clients enforce. Renaming in place
                # is safe: Component.key is a property derived from .name, so
                # the target registers the tool under its new name.
                prefixed = f"{api_name}_{tool.name}"
                tool.name = _fit_name(prefixed, used_tool_names)
                used_tool_names.add(tool.name)
                target.add_tool(tool)
        else:
            # A spec that parses but yields no tools is a property of that one
            # API, not a reason to lose every other API in the set.
            logger.warning(
                f"API '{api_name}' contributed no tools; skipping it. Its spec "
                "parsed but produced no callable operations."
            )

        # Merge prompts
        prompts = await server.list_prompts()
        if prompts:
            for prompt in prompts:
                # Rename the prompt by prefixing with API name, keeping it
                # within the 64-char limit that MCP clients enforce.
                prefixed = f"{api_name}_{prompt.name}"
                prompt.name = _fit_name(prefixed, used_prompt_names)
                used_prompt_names.add(prompt.name)
                target.add_prompt(prompt)
            logger.debug(f"Merged {len(prompts)} prompts from {api_name}")

    return target


async def merge_mcp_servers(
    list_of_servers: list[FastMCP], merged_name: str = "merged_mcp"
) -> FastMCP:
    """
    Merges a list of FastMCP instances into
    a single FastMCP instance by combining their
    tools, prefixing tool names with the server's
    name (API name) to avoid conflicts.

    Args:
        list_of_servers: List of FastMCP instances to merge.
        merged_name: Name for the merged FastMCP instance.

    Returns:
        A new FastMCP instance with renamed tools from all input servers.
    """
    return await _merge_servers_into(FastMCP(merged_name), list_of_servers)


async def get_merged_mcp_server(
    smartapi_q: str | None = None,
    smartapi_id: str | None = None,
    smartapi_ids: list[str] | None = None,
    smartapi_exclude_ids: list[str] | None = None,
    api_set: str | None = None,
    server_name: str = "smartapi_mcp",
) -> FastMCP:
    logger.debug(f"api_set: {api_set}")
    if api_set:
        api_set_args = get_predefined_api_set(api_set)
        if "smartapi_ids" in api_set_args:
            smartapi_ids = api_set_args["smartapi_ids"]
        if "smartapi_q" in api_set_args:
            smartapi_q = api_set_args["smartapi_q"]
        if "smartapi_exclude_ids" in api_set_args:
            smartapi_exclude_ids = api_set_args["smartapi_exclude_ids"]
        logger.debug(f"api_set_args: {api_set_args}")
    logger.debug(f"smartapi_ids: {smartapi_ids}")
    logger.debug(f"smartapi_q: {smartapi_q}")
    logger.debug(f"smartapi_exclude_ids: {smartapi_exclude_ids}")
    if smartapi_q:
        smartapi_ids = await get_smartapi_ids(smartapi_q)
    if smartapi_id:
        smartapi_ids = [smartapi_id]
    if smartapi_ids:
        smartapi_ids = list(set(smartapi_ids))
    if not smartapi_ids:
        err_msg = "No SmartAPI IDs provided or found with the given query."
        raise ValueError(err_msg)
    smartapi_exclude_ids = smartapi_exclude_ids or []
    wanted = [sid for sid in smartapi_ids if sid not in smartapi_exclude_ids]
    list_of_servers, _failures = await build_api_servers(wanted)
    merged_server = await merge_mcp_servers(list_of_servers, server_name)
    logger.info(
        f"Merged {len(list_of_servers)} of {len(wanted)} APIs into one MCP server."
    )
    return merged_server


async def _resolve_smartapi_ids(
    smartapi_q: str | None = None,
    smartapi_id: str | None = None,
    smartapi_ids: list[str] | None = None,
    smartapi_exclude_ids: list[str] | None = None,
    api_set: str | None = None,
) -> list[str]:
    """Resolve the various ID sources into a deduped, exclusion-filtered list."""
    if api_set:
        api_set_args = get_predefined_api_set(api_set)
        smartapi_ids = api_set_args.get("smartapi_ids", smartapi_ids)
        smartapi_q = api_set_args.get("smartapi_q", smartapi_q)
        smartapi_exclude_ids = api_set_args.get(
            "smartapi_exclude_ids", smartapi_exclude_ids
        )

    if smartapi_q:
        smartapi_ids = await get_smartapi_ids(smartapi_q)
    if smartapi_id:
        smartapi_ids = [smartapi_id]

    if smartapi_ids:
        # Dedupe while preserving order (stable, unlike set()).
        smartapi_ids = list(dict.fromkeys(smartapi_ids))
    if not smartapi_ids:
        err_msg = "No SmartAPI IDs provided or found with the given query."
        raise ValueError(err_msg)

    exclude = set(smartapi_exclude_ids or [])
    return [sid for sid in smartapi_ids if sid not in exclude]


async def build_server_for_set(
    smartapi_q: str | None = None,
    smartapi_id: str | None = None,
    smartapi_ids: list[str] | None = None,
    smartapi_exclude_ids: list[str] | None = None,
    api_set: str | None = None,
    server_name: str = "smartapi_mcp",
    *,
    facade: str = "auto",
    facade_threshold: int = 10,
    facade_strict: bool = False,
    tool_search: str = "auto",
    tool_search_max_results: int = 10,
    tool_search_threshold: int = TOOL_SEARCH_AUTO_THRESHOLD,
) -> FastMCP:
    """Build the MCP server for an API set, picking the right strategy.

    For large BioThings sets the **generic facade** (a fixed ~5 tools where the
    target API is a parameter) is used to avoid the 200+ per-API tool explosion.
    For a **mixed** set, the result is a *hybrid* server: the BioThings APIs are
    served through the facade while any non-BioThings APIs are added as faithful
    per-API tools in the same server, so nothing is lost. ``facade`` is one of
    ``"auto"`` (facade when enough APIs in the set are BioThings),
    ``"on"`` (force facade for the BioThings subset), or ``"off"`` (always emit
    per-API tools for every API).

    ``facade_strict`` (default ``False``) controls handling of the rare
    BioThings APIs that expose endpoints beyond the standard interface (e.g.
    SemmedDB's ``/query/ngd``). When ``False``, all BioThings APIs go through the
    facade and those extra endpoints are not reachable (fast startup, no spec
    downloads). When ``True``, each BioThings spec is inspected and any API with
    extra endpoints is served with faithful per-API tools instead (slower
    startup; downloads specs upfront).

    ``tool_search`` (see :data:`TOOL_SEARCH_MODES`, default ``"auto"``)
    additionally collapses the tool listing behind a search interface, which is
    the answer to the per-API tool explosion when the facade does not apply.
    Facade tools are pinned so they stay listed, giving a hybrid server whose
    BioThings half is answered by the facade and whose per-API half is
    discovered by search. ``"auto"`` engages only once the merged server has
    ``tool_search_threshold`` tools; ``tool_search_max_results`` caps hits per
    search.
    """
    available_ids = await _resolve_smartapi_ids(
        smartapi_q=smartapi_q,
        smartapi_id=smartapi_id,
        smartapi_ids=smartapi_ids,
        smartapi_exclude_ids=smartapi_exclude_ids,
        api_set=api_set,
    )

    if facade != "off":
        registry = await build_registry(available_ids)
        # TRAPI services carry the "biothings" tag but are not annotation APIs;
        # is_biothings_family excludes them so they fall through to the
        # non_biothings_ids branch below and get faithful per-API tools.
        biothings = {
            name: entry
            for name, entry in registry.items()
            if is_biothings_family(entry)
        }
        if facade == "on" and not biothings:
            logger.warning(
                "facade='on' but no BioThings APIs were found in the set; "
                "falling back to per-API tools."
            )
        use_facade = bool(biothings) and (
            facade == "on" or len(biothings) >= facade_threshold
        )
        if use_facade:
            if facade_strict:
                # Inspect specs: only fully-standard BioThings APIs go in the
                # facade; ones with extra endpoints fall back to per-API tools.
                facade_entries, extra_bt_ids = await partition_biothings(biothings)
            else:
                # Fast path: assume every BioThings API is fully standard.
                facade_entries, extra_bt_ids = biothings, []
            non_biothings_ids = [
                entry.smartapi_id
                for name, entry in registry.items()
                if name not in biothings
            ]
            per_api_ids = non_biothings_ids + extra_bt_ids

            if facade_entries:
                server = build_biothings_facade(facade_entries, server_name)
                # Capture the facade tools before merging per-API servers so
                # tool search can pin them and collapse only the long tail.
                # Skipped entirely when tool search is off, to keep the default
                # path free of extra work.
                facade_tool_names: list[str] = (
                    [tool.name for tool in await server.list_tools()]
                    if tool_search != "off"
                    else []
                )
                if per_api_ids:
                    logger.info(
                        f"Hybrid server: facade over {len(facade_entries)} "
                        f"BioThings API(s) + per-API tools for "
                        f"{len(per_api_ids)} other API(s)."
                    )
                    extra_servers, _failures = await build_api_servers(per_api_ids)
                    await _merge_servers_into(server, extra_servers)
                else:
                    logger.info(
                        f"Using BioThings facade for {len(facade_entries)} APIs "
                        f"(server_name={server_name})."
                    )
                return await apply_tool_search(
                    server,
                    tool_search,
                    max_results=tool_search_max_results,
                    always_visible=facade_tool_names,
                    threshold=tool_search_threshold,
                )
            logger.info(
                "No APIs qualified for the BioThings facade; using per-API tools."
            )

    logger.info(f"Using per-API tools for {len(available_ids)} APIs.")
    server = await get_merged_mcp_server(
        smartapi_ids=available_ids,
        server_name=server_name,
    )
    return await apply_tool_search(
        server,
        tool_search,
        max_results=tool_search_max_results,
        threshold=tool_search_threshold,
    )
