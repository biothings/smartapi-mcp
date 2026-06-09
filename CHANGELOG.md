# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
