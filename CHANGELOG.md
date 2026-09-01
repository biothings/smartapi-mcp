# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`--tool-search auto` is now the default** (env `SMARTAPI_TOOL_SEARCH`). Search
  turns on once the merged server reaches `--tool-search-threshold` tools
  (default 50, env `TOOL_SEARCH_THRESHOLD`); smaller catalogs keep their direct
  listing. Combined with the BioThings facade this gives a hybrid server: the
  facade answers BioThings queries directly (lexical search is weakest there,
  because the generated per-API descriptions are near-identical boilerplate) and
  search covers the non-BioThings tail (where it measures 79-86% recall@10).
  **This changes default behaviour** for sets above the threshold: e.g. a
  `biothings_all` per-API server previously listed ~314 tools and now lists 2.
  Pass `--tool-search off` to restore the old behaviour.
- **`--tool-search {off,bm25,regex}`** (env `SMARTAPI_TOOL_SEARCH`): collapses the
  tool *listing* behind a search interface instead of listing every tool, using
  fastmcp 3's search transforms. Clients see `search_tools` and `call_tool` and
  discover tools on demand; every tool stays callable through `call_tool`. This
  addresses the per-API tool explosion where the BioThings facade does not apply
  (`biothings_all` is ~50 APIs at ~6 tools each). Facade tools are pinned so they
  stay listed and only the per-API long tail is collapsed.
  `--tool-search-max-results` (env `TOOL_SEARCH_MAX_RESULTS`) caps the hits per
  search; the default is **10** (measured recall@10 vs recall@5: BioThings
  65%->80%, non-BioThings 79%->86%, for roughly 1k extra tokens per search).
  Results are serialized as Markdown, roughly half the size of fastmcp's default
  JSON serialization.
- `apply_tool_search()` in `smartapi_mcp.server` for programmatic use, plus
  `tool_search` / `tool_search_max_results` / `tool_search_threshold` arguments on
  `build_server_for_set()`.

### Fixed
- **Environment variables for `--facade`, `--facade-threshold`, `--tool-search` and
  `--tool-search-max-results` were ignored when running via the CLI.** `load_config`
  assigns from `args` whenever the attribute is truthy, so a non-`None` argparse
  default (`"auto"`, `10`, `"off"`, `5`) silently overwrote the environment on every
  invocation — `SMARTAPI_FACADE=off` had no effect despite being documented in
  `--help`. Those four defaults are now `None`, leaving the effective defaults on
  `Config`, so precedence is CLI > environment > default. (`FACADE_STRICT` was
  unaffected: `store_true` defaults to `False`, which is falsy.)

### Changed
- **Migrated to `fastmcp` 3.x and `awslabs_openapi_mcp_server` 1.x.** Both pins
  moved together (`fastmcp>=3.3.1,<4`, `awslabs_openapi_mcp_server>=1.1.5,<2`)
  because the two projects migrated in lockstep. The 2.x/0.2.x lines are no
  longer maintained upstream (last releases 2026-04-13 and 2026-03-27).
- `_merge_servers_into()` now uses `FastMCP.list_tools()` / `list_prompts()`,
  which replaced the dict-returning `get_tools()` / `get_prompts()` in fastmcp
  3.x. Merged tool/prompt names, the 64-character cap, and collision handling
  are unchanged.
- Merge tests now build real `Tool` / `Prompt` objects instead of `MagicMock`s:
  fastmcp 3's `add_tool()` coerces non-`Tool` inputs via `Tool.from_function()`,
  which rejects mocks. This closes a gap where the old tests could not have
  caught a malformed component being registered.

## [0.3.2] - 2026-06-17

### Fixed
- **Tool and prompt names are now capped at 64 characters** when merging per-API
  servers into a single server. MCP clients (including the Claude frontend)
  reject longer names, which could drop tools/prompts from APIs with long names.
  Over-long prefixed names are deterministically truncated with a short hash
  suffix that keeps them unique and collision-free.

### Changed
- The CLI `--help` output now lists the corresponding environment variable
  (e.g. `[env: SMARTAPI_API_SET]`) for each option that can be set via the
  environment.

## [0.3.1] - 2026-06-09

### Added
- Declared and tested support for **Python 3.14**: added the `3.14` classifier
  and extended the CI test matrices to `3.10`–`3.14` (also bumped
  `actions/setup-python` to v5). The package runs on the free-threaded 3.14
  build as well, though it offers no meaningful benefit there (the workload is
  I/O-bound and asyncio-based).

## [0.3.0] - 2026-06-09

### Added
- **BioThings generic facade** for large API sets: instead of emitting one tool
  per (API × operation) — 200+ near-duplicate tools for `biothings_all` — the
  server exposes a fixed set of ~5 generic tools (`list_biothings_apis`,
  `biothings_query`, `biothings_get`, `biothings_getbatch`, `biothings_fields`)
  where the target API is a parameter. Keeps tool count and context small on
  every MCP client, with no dependency on `tools/list_changed`.
- **Hybrid servers** for mixed sets: BioThings APIs go through the facade while
  any non-BioThings APIs are added as faithful per-API tools in the same server.
- **`--facade {auto,on,off}`** and **`--facade-threshold`** to control the
  strategy (env: `SMARTAPI_FACADE`, `FACADE_THRESHOLD`).
- **`--facade-strict`** (env: `FACADE_STRICT`) inspects BioThings specs and
  serves any API with non-standard endpoints (e.g. SemmedDB's `/query/ngd`) with
  per-API tools so those endpoints aren't hidden.
- `get_smartapi_registry()` to fetch id/title/description/tags for matching APIs
  in a single registry query.

### Changed
- Pinned dependencies to `awslabs_openapi_mcp_server>=0.2.12,<1` and
  `fastmcp>=2.14,<3` (awslabs 1.x / fastmcp 3.x are not yet supported).
- Added an HTTP request timeout and defensive parsing to SmartAPI registry calls.
- The CLI now exits cleanly with a helpful message (instead of a traceback) when
  no APIs are selected; clarified `--help` text.
- `server_name` default aligned to `smartapi_mcp`.
- CI also emits `coverage.xml` so the Codecov upload works.

### Removed
- The local semantic-search **smart-routing / progressive-loading** feature
  (`router.py`) and the deprecated `--smart-routing` / `--max-context-tools`
  flags and their configuration. The unused `smart-routing` optional-dependency
  group (numpy / sentence-transformers / faiss-cpu) was dropped.

### Fixed
- Fresh installs were resolving to an incompatible `fastmcp` 3.x (which removed
  `FastMCP.get_tools()` and rejects `*args` tools); the new pins prevent this.
- Excluded the SmartAPI registry API (not a BioThings data API) from the
  `biothings_all` set.

## [0.2.0]

- BioThings core API sets, multi-API MCP server, HTTP/stdio transports.
