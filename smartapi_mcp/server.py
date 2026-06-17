"""
SmartAPI MCP Server

Main MCP server implementation for SmartAPI integration.
"""

import hashlib
import re

from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.api.config import Config
from awslabs.openapi_mcp_server.server import create_mcp_server_async
from fastmcp import FastMCP

# Import BioThings generic-facade builder
from .biothings import build_biothings_facade, build_registry, partition_biothings

# Import from smartapi module - avoiding circular imports
from .smartapi import (
    get_base_server_url,
    get_predefined_api_set,
    get_smartapi_ids,
    load_api_spec,
    smartapi_spec_url,
)

# Cap names at 64 characters. The MCP spec (SEP-986) recommends 1-64 chars for
# *tool* names as a SHOULD, but the limit is enforced as a hard error by the
# model APIs: both Anthropic (FrontendRemoteMcpToolDefinition.name; 400 on
# longer names) and OpenAI (^[a-zA-Z0-9_-]{1,64}$) reject names over 64 chars.
# So prefixed per-API names must be truncated to fit. The spec does not define a
# length for *prompt* names, but we cap them too as a harmless safeguard against
# clients that reuse the tool-name validator.
MAX_TOOL_NAME_LEN = 64


async def get_mcp_server(smartapi_id: str) -> FastMCP:
    config = Config(
        api_spec_url=smartapi_spec_url.format(smartapi_id=smartapi_id),
    )
    openapi_spec = load_api_spec(smartapi_id)
    base_server_url = get_base_server_url(openapi_spec)
    config.api_base_url = base_server_url

    return await create_mcp_server_async(config)


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
    logger.debug(f"Name '{name}' exceeds {MAX_TOOL_NAME_LEN} chars or collides; "
                 f"renamed to '{truncated}'.")
    return truncated


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
    used_tool_names: set[str] = set(await target.get_tools())
    used_prompt_names: set[str] = set(await target.get_prompts())
    for server in list_of_servers:
        api_name = re.sub(
            r"[^a-z0-9_-]", "_", getattr(server, "name", "unknown_api").lower()
        )

        tools = await server.get_tools()
        if tools:
            for original_name, tool in tools.items():
                # Rename the tool by prefixing with API name, keeping it within
                # the 64-char limit that MCP clients enforce.
                prefixed = f"{api_name}_{original_name}"
                tool.name = _fit_name(prefixed, used_tool_names)
                used_tool_names.add(tool.name)
                target.add_tool(tool)
        else:
            err_msg = f"Server {server} does not have accessible tools."
            raise AttributeError(err_msg)

        # Merge prompts
        prompts = await server.get_prompts()
        if prompts:
            for original_name, prompt in prompts.items():
                # Rename the prompt by prefixing with API name, keeping it
                # within the 64-char limit that MCP clients enforce.
                prefixed = f"{api_name}_{original_name}"
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
    list_of_servers = [
        await get_mcp_server(sid)
        for sid in smartapi_ids
        if sid not in smartapi_exclude_ids
    ]
    merged_server = await merge_mcp_servers(list_of_servers, server_name)
    logger.info(f"Merged {len(list_of_servers)} APIs into one MCP server.")
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
        biothings = {
            name: entry for name, entry in registry.items() if "biothings" in entry.tags
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
                if per_api_ids:
                    logger.info(
                        f"Hybrid server: facade over {len(facade_entries)} "
                        f"BioThings API(s) + per-API tools for "
                        f"{len(per_api_ids)} other API(s)."
                    )
                    extra_servers = [await get_mcp_server(sid) for sid in per_api_ids]
                    await _merge_servers_into(server, extra_servers)
                else:
                    logger.info(
                        f"Using BioThings facade for {len(facade_entries)} APIs "
                        f"(server_name={server_name})."
                    )
                return server
            logger.info(
                "No APIs qualified for the BioThings facade; using per-API tools."
            )

    logger.info(f"Using per-API tools for {len(available_ids)} APIs.")
    return await get_merged_mcp_server(
        smartapi_ids=available_ids,
        server_name=server_name,
    )
