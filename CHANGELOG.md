# Changelog

All notable changes to this project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `smartapi_mcp/openapi.py`: `fetch_spec()`, `validate_spec()`,
  `reject_external_refs()`, `resolve_internal_refs()` and
  `build_openapi_server()`, replacing the awslabs loader, validator and server
  builder. Specs are cached for an hour (the `--facade-strict` path loads a spec
  to inspect it, then loads it again to build from it).

- `smartapi_mcp/log.py`: the `logger` / `get_format()` that the other modules
  previously imported from awslabs. Same loguru format, same stderr sink, same
  default level, so log output is unchanged.

### Changed

- **`Config` is now a standalone dataclass** and no longer subclasses
  `awslabs.openapi_mcp_server.api.config.Config`. It carries the 17 fields this
  package reads; the ~35 inherited ones covered authentication schemes, Cognito,
  tag filtering and multi-spec composition that SmartAPI's public APIs never
  used. Code doing `isinstance(config, awslabs...Config)` will need updating.

- `SERVER_HOST`, `SERVER_PORT`, `SERVER_TRANSPORT`, `API_SPEC_URL` and
  `API_BASE_URL` are now read by this package's own `load_config` rather than
  inherited from awslabs. The remaining awslabs environment variables
  (`AUTH_*`, `INCLUDE_TAGS`, `EXCLUDE_TAGS`, `VALIDATE_OUTPUT`,
  `ADDITIONAL_SPECS`, `API_SPEC_PATH`, `SERVER_DEBUG`,
  `SERVER_MESSAGE_TIMEOUT`, `ALLOW_*`) are no longer recognised; none of them
  affected this package's behaviour.

- `tests/test_config.py` was rewritten against real behaviour. It previously
  spent most of its length mocking the awslabs base config and the
  `dataclasses.fields` copy loop, and asserted exact logger call strings; it now
  covers defaults, environment parsing, integer/bool coercion, CLI precedence
  and the malformed-value fallbacks. New `tests/test_openapi.py` covers the
  replacement module offline via `httpx.MockTransport`, including the ref-cycle,
  depth-cut, SSRF-refusal, retry and cache paths. Test count 122 → 183.

- Dropped two stale `pyproject.toml` references to `smartapi_mcp/awslabs_server.py`,
  a file that has not existed for several releases.

### Fixed

- **Response `$ref`s are now resolved for tool descriptions.** fastmcp resolves
  references for the input schemas it generates but leaves them in the response
  schemas it hands to the description formatter, so an operation whose response
  is a `$ref` was documented as returning nothing in particular. awslabs papered
  over this with prance, which fails on the recursive schemas TRAPI APIs use and
  silently fell back to unresolved parsing. `resolve_internal_refs()` handles
  them, which accounts for 33 of the 45 changed tools across 6 APIs — every one
  of them longer (ClinGen: +426 to +642 characters per tool; one Translator
  status endpoint +1,637).
  Only the *description* path uses the resolved copy; the pristine spec still
  goes to fastmcp, so shared and recursive definitions stay behind `$defs`.
  Pre-resolving the whole spec instead inflated one TRAPI tool's input schema
  from 67 KB to 115 KB.

- **`$ref`s standing in for a whole Parameter Object are now inlined.** fastmcp
  resolves references *inside* schemas but ignores one used in place of an
  entire Parameter / Request Body / Response Object, so such a parameter arrived
  with an empty schema — MyTaxon.info's `callback` parameter came through as
  `{}`, losing its type and description. The awslabs loader avoided this only
  incidentally, by pre-resolving the whole document with prance.
  `build_openapi_server()` now inlines every internal `$ref` *except*
  `#/components/schemas/` ones, which are left for fastmcp to hoist into
  `$defs`.

- **Sibling keys alongside a `$ref` now win over the referenced target**, as
  JSON Schema specifies. prance discarded them, so a field written as
  `{"$ref": ".../BiolinkEntity", "description": "Subject node category...",
  "example": "biolink:ChemicalEntity"}` was documented with `BiolinkEntity`'s
  generic description and example instead of its own. This accounts for 12 of
  the 45 changed tools, all in the two BTE TRAPI APIs: 8 input schemas gained
  per-field descriptions, examples and patterns, and 4 descriptions now quote
  the spec's own example (which is 20 characters shorter than the generic one it
  replaces).

- **`--tool-search-threshold` had no effect.** The flag and its
  `TOOL_SEARCH_THRESHOLD` environment variable were parsed into `Config` but
  never passed to `build_server_for_set()`, so the threshold was always the
  50-tool default no matter what was configured.

- **`--port` was ignored, and would have shadowed `SERVER_PORT` if wired up.**
  `load_config` never read `args.port` or `args.host`, so only the environment
  variables worked; and `--port`'s argparse default of `8000` would have
  overwritten `SERVER_PORT` on every run once it was read (the same bug class
  fixed for `--facade` / `--tool-search` earlier in this release). Both flags now
  work, with CLI > environment > default precedence, and `--port`'s default is
  `None`.

- An unusable spec now raises instead of being logged as
  "validation failed, but continuing anyway" and passed on regardless.
  `build_api_servers()` already catches per-API failures and skips that API with
  a warning, so the caller gets a clean skip rather than a spec that fastmcp will
  choke on later. `SpecError` subclasses `ValueError`, so existing handlers still
  catch it.

- A 4xx spec fetch is no longer retried three times with exponential backoff. An
  unknown SmartAPI id returns 404 on every attempt, so the retries only added
  ~3 s per bad id when building a large set.

### Removed

- **Dropped the `awslabs_openapi_mcp_server` dependency.** By its 1.x line that
  package had converged on being a thin wrapper over `FastMCP.from_openapi()`,
  so `smartapi_mcp/openapi.py` now calls fastmcp directly. Verified against a
  recording of the old path over **107 of the registry's 108 uptime-passing
  APIs** (`scripts/check_spec_parity.py`): 92 of 107 build, exactly as before,
  with identical tool names and no API newly failing. Of the 592 resulting
  tools, **547 are byte-identical**; the other 45 all gain detail rather than
  lose it (see *Fixed* below). A clean install goes from **87 packages /
  91 MB to 68 packages / 56 MB** — 18 transitive dependencies removed and none
  added. The largest is boto3/botocore (20 MB), pulled in only for a Cognito
  auth provider this package never used, and which no longer even imported
  cleanly in a fresh 3.14 environment. Also gone: prance, ruamel.yaml, bcrypt,
  openapi-spec-validator, openapi-schema-validator, tenacity, requests,
  urllib3, chardet, charset-normalizer, jmespath, s3transfer, python-dateutil,
  rfc3339-validator, lazy-object-proxy and six. `httpx` and `loguru` become
  direct dependencies; both were already installed transitively, so neither is
  a new download.

- **Per-operation MCP prompts are no longer generated.** The awslabs wrapper
  emitted one prompt per operation for specs carrying `operationId`s — 10 of the
  30 APIs measured, all non-BioThings — and each prompt restated its own tool's
  name, method, path, parameters and response codes. Beyond being redundant,
  prompts are *not* collapsed by `--tool-search` (the transform filters
  `tools/list` only), so on a large set they were context cost that search could
  not hide. **This changes behaviour** for sets containing such APIs:
  `prompts/list` is now empty.

- Several awslabs features were never reachable and are simply gone: a
  `health_check` tool that was defined but never registered, an API resource
  handler registered against a `server.register_resource_handler` hook that
  FastMCP does not have, route maps forcing GET-with-query-params to
  `MCPType.TOOL` (fastmcp 3 already defaults every route to a tool), five unused
  auth providers, and a metrics registry that only awslabs' own
  `make_request_with_retry` recorded to — so the "Final metrics" line logged on
  shutdown was always an empty summary. That line is removed.

## [0.4.0] - 2026-09-02

### Added
- **`CORE_BIOTHINGS_API_IDS`** in `smartapi_mcp.smartapi`: the canonical,
  broad-coverage BioThings annotation services, as distinct from the ~50
  single-source satellite APIs. `biothings_core` and `biothings_test` are now
  derived from it, so "which APIs are core" is stated once instead of being
  duplicated per preset.

- **`--tool-search auto` is now the default** (env `SMARTAPI_TOOL_SEARCH`). Search
  turns on once the merged server reaches `--tool-search-threshold` tools
  (default 15, env `TOOL_SEARCH_THRESHOLD`); smaller catalogs keep their direct
  listing. Combined with the BioThings facade this gives a hybrid server: the
  facade answers BioThings queries directly (lexical search is weakest there,
  because the generated per-API descriptions are near-identical boilerplate) and
  search covers the non-BioThings tail (where it measures 79-86% recall@10).
  **This changes default behaviour** for sets above the threshold: e.g. a
  `biothings_all` per-API server previously listed ~314 tools and now lists 2.
  Pass `--tool-search off` to restore the old behaviour.
- **`--tool-search {auto,off,bm25,regex}`** (env `SMARTAPI_TOOL_SEARCH`): collapses the
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
- **TRAPI services are no longer served through the BioThings facade.**
  BioThings Explorer and Service Provider carry the `biothings` tag but speak
  the Translator Reasoner query-graph protocol, not the BioThings annotation
  interface, so none of the generic facade tools apply. They are now excluded by
  the new `is_biothings_family()` predicate (tagged `biothings` *and* not
  `trapi`) and served with faithful per-API tools instead.
  This was returning wrong answers, not merely hiding endpoints: the facade
  infers an entity type from the first `/{type}/{id}`-shaped path, and BTE's
  `GET /asyncquery_status/{id}` matches that shape, so `biothings_get` would
  request `/asyncquery_status/<id>` and hand back a job status as though it were
  an annotation record — with no error. `biothings_all` avoided this via its
  `NOT tags.name=trapi` filter, but any set assembled by id or by a
  `tags.name:biothings` query did not.
- **The facade's `list_biothings_apis` ranking was scoring by verbosity.**
  `rank_apis()` summed `str.count()` of every query token over the raw API text,
  so (a) stopwords dominated — "get a gene annotation by its Entrez gene id" was
  driven by "get"/"a"/"by"/"its"/"id" — (b) substrings matched, with "id" hitting
  inside "identifier", "candidate" and "provide", and (c) repetition was
  rewarded, ranking MyGeneSet above MyGene. It now uses word-boundary tokens,
  a stopword list, binary term frequency, Robertson/Sparck-Jones IDF, and 3x
  weighting for name/title/tag hits over description hits. Measured on 20
  BioThings intents against the live registry: **recall@10 75% -> 85%,
  recall@5 70% -> 80%**, which brings facade discovery level with the BM25
  tool-search path.

- **A single unloadable API no longer aborts the whole server.** Per-API servers
  were built with a bare list comprehension, so one bad spec took down every
  other API in the set. Measured against the registry's uptime-passing set, 15
  of 107 APIs (about one in seven) fail to load -- external `$ref`s (refused by
  awslabs 1.x as an SSRF guard), invalid OpenAPI schemas, missing `servers`
  blocks -- which made `--smartapi_q '_status.uptime_status:pass'` impossible to
  start at all. Those APIs are now skipped with a warning and a summary count,
  and the rest are served. New `build_api_servers()` returns
  `(servers, failures)` for callers that want the detail.
  This also catches `SystemExit`, not just `Exception`: awslabs reports *every*
  spec error by calling `sys.exit(1)` from inside the library, so a spec that
  fastmcp itself rejected (e.g. an OpenAPI 3.0 document using `"type": "null"`)
  still aborted the whole build. It killed a 27-API run at API 17 against the
  uptime-passing set.
- **A spec that parses but yields no tools is now a warning, not an error.**
  `_merge_servers_into()` raised `AttributeError` in that case, which likewise
  discarded every other API in the set.
- **Environment variables for `--facade`, `--facade-threshold`, `--tool-search` and
  `--tool-search-max-results` were ignored when running via the CLI.** `load_config`
  assigns from `args` whenever the attribute is truthy, so a non-`None` argparse
  default (`"auto"`, `10`, `"off"`, `5`) silently overwrote the environment on every
  invocation — `SMARTAPI_FACADE=off` had no effect despite being documented in
  `--help`. Those four defaults are now `None`, leaving the effective defaults on
  `Config`, so precedence is CLI > environment > default. (`FACADE_STRICT` was
  unaffected: `store_true` defaults to `False`, which is falsy.)

### Changed
- **`biothings_core` now includes MyTaxon.info, so the preset is 6 APIs, not 5**
  (and `biothings_test` is 7). MyTaxon is a core `My*` annotation service by
  every other measure and was the odd one out.
- **The facade's `list_biothings_apis` now prefers the core APIs** when several
  APIs match a query, via a `CORE_API_BOOST` multiplier of 1.2 in `rank_apis()`.
  Broad-coverage services are the *worst* served by pure lexical scoring --
  being general means their descriptions carry the least distinctive vocabulary,
  while single-source satellites read as highly specific -- so a lexical ranker
  systematically under-ranks exactly the APIs a user most often wants.
  The boost is multiplicative, so a zero score stays zero and a core API is
  never promoted into a query it does not match.
  Measured on 20 BioThings intents: with the registry descriptions as they are
  today, recall@5 goes 16/20 -> 19/20 (MRR 0.71 -> 0.82) and the core-API
  intents go 3/6 -> 6/6. 1.2 is deliberately the smallest value that captures
  the benefit: larger values add no recall and cost ranking quality once the
  registry metadata improves (at 3.0, MRR against enriched descriptions falls
  from 0.90 to 0.81).
  A metadata PR enriching those descriptions is under review upstream
  (NCATS-Tangerine/translator-api-registry#168); with it merged the same
  benchmark reaches 20/20 at MRR 0.90, and the boost becomes a small safety
  margin rather than the mechanism.

- **`--tool-search-threshold` defaults to 15** (env `TOOL_SEARCH_THRESHOLD`).
  This flag is new in this release, so 15 is its first shipped default; it was
  tuned down from an initial 50 during development.
  Measured over the registry's uptime-passing set
  (592 tools, 92 APIs), one entry in `tools/list` — name plus enriched
  description plus JSON input schema — averages ~3,900 characters (~975 tokens),
  median ~1,270 (~320), p90 ~7,500, with one TRAPI tool at 84,000 (~21,000
  tokens). The old default therefore let a listing reach roughly 16k tokens of
  median-sized tools or 51k of mean-sized ones before search engaged;
  `biothings_core --facade off` is 30 tools and measures ~31k tokens. The new
  default caps that at roughly 5-15k while still leaving a single API (~6 tools)
  and the facade (~5 tools) directly listed.
  Note the 65x spread in per-tool size: tool *count* is a crude proxy for
  payload size, and a token budget would be the better instrument — the constant
  is documented as a floor pending that change.

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
