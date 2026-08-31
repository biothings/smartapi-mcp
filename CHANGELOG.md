# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
