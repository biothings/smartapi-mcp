"""
OpenAPI spec loading and MCP server construction.

Replaces the parts of ``awslabs.openapi_mcp_server`` this package used to call:
``utils.openapi.load_openapi_spec``, ``utils.openapi_validator``, and
``server.create_mcp_server_async``. By awslabs 1.x that last function had become
a wrapper over :meth:`fastmcp.FastMCP.from_openapi` plus a description enricher,
so calling ``from_openapi`` directly here loses nothing and drops a dependency
tree of ~24 MB (boto3/botocore for a Cognito auth provider we never use, prance,
bcrypt, and several others) along with a handful of features that never applied:
five unused auth providers, a health-check tool that was defined but never
registered, a resource handler registered against a FastMCP hook that does not
exist, and route maps that forced GET-with-query-params to be tools -- which
fastmcp 3 already does by default.

Two behaviours from the awslabs loader are deliberately kept:

* **External ``$ref``s are refused** (:func:`reject_external_refs`). A spec is
  third-party content fetched from the registry, and an external reference is a
  request for *us* to fetch an arbitrary URL or local file on its behalf.
* **Response ``$ref``s are resolved** (:func:`resolve_internal_refs`) so tool
  descriptions document what an operation returns. awslabs got this from prance;
  prance fails on the recursive schemas that TRAPI APIs use and silently falls
  back to unresolved parsing, so the resolver here is both smaller and more
  complete (measured: ClinGen's descriptions go from 16,910 to 22,062 chars).

The DNS-pinned fetch in the awslabs loader is *not* kept. It guards against a
hostile, caller-supplied spec URL; the only URL this package fetches is the
hardcoded ``smart-api.info`` metadata endpoint, so there is no attacker-chosen
host to pin. (The API *base* URL does come from third-party spec content, but it
was never validated by awslabs either -- that is unchanged here.)
"""

import json
import time
from typing import Any

import httpx2
from fastmcp import FastMCP
from fastmcp.utilities.openapi import format_description_with_responses

from .log import logger

__all__ = [
    "SpecError",
    "build_openapi_server",
    "fetch_spec",
    "reject_external_refs",
    "resolve_internal_refs",
    "validate_spec",
]

# Upper bound on a fetched spec body. Real OpenAPI documents fit comfortably --
# the largest in the registry (SemmedDB) is ~4 MiB -- while the cap stops a
# misbehaving endpoint from exhausting memory.
MAX_SPEC_BYTES = 10 * 1024 * 1024

# Retries for a spec fetch, with exponential backoff between attempts. The
# registry occasionally refuses connections when many specs are fetched in
# sequence, and one refusal should not drop an API from the server.
SPEC_FETCH_ATTEMPTS = 3

# How long a parsed spec stays cached. Specs are fetched more than once per run
# (``--facade-strict`` inspects a spec, then builds a server from it), and they
# do not change within a run.
SPEC_CACHE_TTL = 3600.0

# Timeout for a single spec fetch.
SPEC_FETCH_TIMEOUT = 30.0

# Status codes at or above this are server-side and worth retrying; below it
# the request itself is at fault and will fail identically on every attempt.
HTTP_SERVER_ERROR = 500

# References under this pointer are left for fastmcp to resolve; see
# :func:`build_openapi_server`.
SCHEMA_REF_PREFIX = "#/components/schemas/"

# Depth at which :func:`resolve_internal_refs` stops expanding. Recursive
# schemas (TRAPI's ``Attribute`` contains a list of ``Attribute``) would
# otherwise expand forever; the cycle check catches direct recursion and this
# catches the mutual kind.
MAX_REF_DEPTH = 12


class SpecError(ValueError):
    """An OpenAPI spec is missing, malformed, or refuses to be loaded safely."""


def validate_spec(spec: Any) -> dict[str, Any]:
    """Return ``spec`` if it is a usable OpenAPI 3 document, else raise.

    This is the same check the awslabs validator performed in practice. That
    function looked like it did more -- it had a second pass through
    ``openapi_core`` -- but ``openapi_core`` is neither declared as a dependency
    nor installed, so the branch never ran, and even when it did it returned
    ``True`` on failure. The three key checks below are the real behaviour.
    """
    if not isinstance(spec, dict):
        err_msg = (
            f"OpenAPI spec must be a mapping at its root, got {type(spec).__name__}"
        )
        raise SpecError(err_msg)
    for key in ("openapi", "info", "paths"):
        if key not in spec:
            err_msg = f"OpenAPI spec is missing the required {key!r} field"
            raise SpecError(err_msg)
    version = str(spec["openapi"])
    if not version.startswith("3."):
        # Warn rather than refuse: fastmcp may still make sense of it, and
        # refusing would drop an API that currently works.
        logger.warning(
            f"OpenAPI version {version} may not be fully supported "
            "(3.x is expected); continuing anyway."
        )
    return spec


def reject_external_refs(node: Any) -> None:
    """Raise :class:`SpecError` if ``node`` contains a non-internal ``$ref``.

    Only in-document references (starting with ``#``) are allowed. An
    ``http(s)://``, ``file://``, or relative-path ``$ref`` in a registry-hosted
    spec is a request for this process to fetch a URL or read a local file
    chosen by whoever published the spec, which is a server-side request forgery
    / local file disclosure vector. Refusing means a handful of registry APIs
    cannot be served; that is the intended trade.
    """
    if isinstance(node, dict):
        ref = node.get("$ref")
        if isinstance(ref, str) and not ref.startswith("#"):
            err_msg = (
                f"Refusing to resolve external $ref {ref!r} in OpenAPI spec; only "
                'internal references (starting with "#") are allowed. External '
                "http(s)://, file://, and relative-path references are blocked to "
                "prevent SSRF and local file disclosure."
            )
            raise SpecError(err_msg)
        for value in node.values():
            reject_external_refs(value)
    elif isinstance(node, list):
        for item in node:
            reject_external_refs(item)


def _parse_spec_bytes(content: bytes) -> dict[str, Any]:
    """Parse spec bytes as JSON, falling back to YAML when PyYAML is present.

    The SmartAPI metadata endpoint always serves JSON, so the YAML path is a
    convenience for callers passing their own content. PyYAML is not declared as
    a dependency; if it is absent, a YAML document raises :class:`SpecError`
    naming the missing package rather than an opaque JSON error.
    """
    try:
        return validate_spec(json.loads(content))
    except json.JSONDecodeError as json_err:
        try:
            # Imported lazily on purpose: PyYAML is not a declared dependency,
            # and the SmartAPI metadata endpoint only ever serves JSON.
            import yaml  # noqa: PLC0415
        except ImportError:
            err_msg = (
                "Spec is not valid JSON and YAML parsing requires PyYAML "
                "(pip install pyyaml)"
            )
            raise SpecError(err_msg) from json_err
        try:
            parsed = yaml.safe_load(content)
        except yaml.YAMLError as yaml_err:
            err_msg = f"Spec is neither valid JSON nor valid YAML: {yaml_err}"
            raise SpecError(err_msg) from yaml_err
        return validate_spec(parsed)


# Parsed specs, keyed by URL: ``{url: (fetched_at, spec)}``. Entries are handed
# out by reference, so callers must not mutate what they receive --
# :func:`resolve_internal_refs` builds a new structure rather than editing in
# place for exactly this reason.
_spec_cache: dict[str, tuple[float, dict[str, Any]]] = {}


def clear_spec_cache() -> None:
    """Drop every cached spec. Intended for tests."""
    _spec_cache.clear()


def fetch_spec(url: str, *, use_cache: bool = True) -> dict[str, Any]:
    """Fetch, parse and validate the OpenAPI spec at ``url``.

    Retries transient network failures up to :data:`SPEC_FETCH_ATTEMPTS` times
    with exponential backoff. Results are cached for :data:`SPEC_CACHE_TTL`
    seconds. Raises :class:`SpecError` for a spec that is too large, unparseable,
    not OpenAPI 3, or carrying an external ``$ref``; those are properties of the
    spec and will not be fixed by retrying.
    """
    if not url:
        err_msg = "A spec URL is required"
        raise SpecError(err_msg)

    if use_cache:
        cached = _spec_cache.get(url)
        if cached is not None and (time.monotonic() - cached[0]) < SPEC_CACHE_TTL:
            logger.debug(f"Using cached OpenAPI spec for {url}")
            return cached[1]

    logger.info(f"Fetching OpenAPI spec from URL: {url}")
    content: bytes | None = None
    last_error: Exception | None = None
    for attempt in range(SPEC_FETCH_ATTEMPTS):
        try:
            with httpx2.Client(
                timeout=SPEC_FETCH_TIMEOUT, follow_redirects=True
            ) as client:
                response = client.get(url)
                response.raise_for_status()
                content = response.content
            break
        except httpx2.HTTPStatusError as exc:
            # A 4xx is a property of the request, not a transient fault: an
            # unknown SmartAPI id returns 404 on every attempt, so retrying it
            # only adds backoff delay to a failure that is already decided.
            if exc.response.status_code < HTTP_SERVER_ERROR:
                raise
            last_error = exc
        except httpx2.HTTPError as exc:
            last_error = exc

        if attempt < SPEC_FETCH_ATTEMPTS - 1:
            delay = 2**attempt
            logger.warning(
                f"Attempt {attempt + 1} of {SPEC_FETCH_ATTEMPTS} to fetch {url} "
                f"failed: {last_error}. Retrying in {delay}s..."
            )
            time.sleep(delay)

    if content is None:
        logger.error(f"All {SPEC_FETCH_ATTEMPTS} attempts to fetch {url} failed")
        raise last_error or SpecError(f"Could not fetch spec from {url}")

    if len(content) > MAX_SPEC_BYTES:
        err_msg = f"Spec too large: {len(content)} bytes (max {MAX_SPEC_BYTES})"
        raise SpecError(err_msg)

    spec = _parse_spec_bytes(content)
    reject_external_refs(spec)

    if use_cache:
        _spec_cache[url] = (time.monotonic(), spec)
    return spec


def resolve_internal_refs(
    spec: dict[str, Any],
    *,
    max_depth: int = MAX_REF_DEPTH,
    skip_prefixes: tuple[str, ...] = (),
) -> dict[str, Any]:
    """Return a copy of ``spec`` with in-document ``$ref``s inlined.

    References whose pointer starts with any of ``skip_prefixes`` are left
    untouched. :func:`build_openapi_server` uses that to resolve everything
    *except* ``#/components/schemas/``, because fastmcp handles schema
    references itself (and better -- it hoists shared and recursive ones into
    ``$defs``) but silently ignores ``$ref``s at the parameter, request-body and
    response *object* level, which would drop those parameters entirely.

    Recursion is cut two ways: a reference already being expanded on the current
    branch resolves to ``{}``, and expansion stops at ``max_depth``. Both yield
    an empty schema rather than looping, which the formatter renders as "no
    documented properties" -- the same outcome as not resolving at all.

    Sibling keys alongside a ``$ref`` override the referenced target, per JSON
    Schema. That matters: prance (which the awslabs loader used) discarded them,
    so a field documented as ``{"$ref": ".../CURIE", "description": "...",
    "example": "..."}`` lost its specific description and example in favour of
    the generic one on ``CURIE``.

    ``spec`` is not modified. A dangling reference is left in place rather than
    raising, since a partly-documented description beats no server at all.
    """

    def lookup(pointer: str) -> Any:
        node: Any = spec
        for raw in pointer.lstrip("#/").split("/"):
            # JSON Pointer escapes: ~1 is "/" and ~0 is "~", in that order.
            part = raw.replace("~1", "/").replace("~0", "~")
            node = node[int(part)] if isinstance(node, list) else node[part]
        return node

    def walk(node: Any, seen: frozenset[str], depth: int) -> Any:
        if isinstance(node, dict):
            ref = node.get("$ref")
            if (
                isinstance(ref, str)
                and ref.startswith("#")
                and not ref.startswith(skip_prefixes)
            ):
                if ref in seen or depth >= max_depth:
                    return {}
                try:
                    target = lookup(ref)
                except (KeyError, IndexError, ValueError, TypeError):
                    logger.debug(f"Leaving dangling $ref {ref!r} unresolved")
                    return node
                resolved = walk(target, seen | {ref}, depth + 1)
                # Sibling keys alongside a $ref (e.g. an overriding
                # "description") win over the referenced target, per JSON Schema.
                siblings = {
                    key: walk(value, seen, depth)
                    for key, value in node.items()
                    if key != "$ref"
                }
                if isinstance(resolved, dict):
                    return {**resolved, **siblings}
                return resolved
            return {key: walk(value, seen, depth) for key, value in node.items()}
        if isinstance(node, list):
            return [walk(item, seen, depth) for item in node]
        return node

    return walk(spec, frozenset(), 0)


def _response_schemas_by_route(
    spec: dict[str, Any],
) -> dict[tuple[str, str], dict[str, dict[str, Any]]]:
    """Index ``spec``'s response content schemas by ``(path, METHOD)``.

    Built once per server from the ref-resolved spec, so the per-component
    enricher is a dict lookup rather than a re-walk of the document.
    """
    index: dict[tuple[str, str], dict[str, dict[str, Any]]] = {}
    for path, path_item in (spec.get("paths") or {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, operation in path_item.items():
            if not isinstance(operation, dict):
                continue
            by_code: dict[str, dict[str, Any]] = {}
            for code, response in (operation.get("responses") or {}).items():
                if not isinstance(response, dict):
                    continue
                schemas = {
                    media: media_obj["schema"]
                    for media, media_obj in (response.get("content") or {}).items()
                    if isinstance(media_obj, dict) and "schema" in media_obj
                }
                if schemas:
                    by_code[str(code)] = schemas
            if by_code:
                index[path, method.upper()] = by_code
    return index


def build_openapi_server(
    spec: dict[str, Any],
    base_url: str,
    name: str,
    *,
    validate_output: bool = True,
    timeout: float = 30.0,
) -> FastMCP:
    """Build a FastMCP server exposing every operation in ``spec`` as a tool.

    ``name`` becomes the server name, which
    :func:`smartapi_mcp.server._merge_servers_into` turns into the per-API tool
    prefix -- so callers should pass the spec's ``info.title``, as the awslabs
    wrapper did.

    Two differently-resolved copies of ``spec`` are used, because fastmcp splits
    the work with us:

    * The copy handed to fastmcp has every internal ``$ref`` inlined **except**
      those into ``#/components/schemas/``. fastmcp resolves schema references
      itself and does it better -- shared and recursive ones are hoisted into
      ``$defs`` instead of being duplicated, which on a TRAPI API is the
      difference between a 67 KB and a 115 KB input schema. But it silently
      ignores ``$ref``s at the parameter / request-body / response *object*
      level, so those must be inlined here or the parameters vanish (measured on
      MyTaxon.info: a ``$ref``-ed ``callback`` parameter arrived as ``{}``).
    * A fully-resolved copy feeds the description formatter, so an operation
      whose response is a ``$ref`` is documented with the properties it actually
      returns.

    Descriptions are otherwise enriched exactly as the awslabs wrapper did, by
    fastmcp's own :func:`format_description_with_responses`.

    No prompts are generated. The awslabs wrapper emitted one prompt per
    operation for specs carrying ``operationId``s, restating the tool's own name,
    method, path and parameters. Beyond being redundant, prompts are not
    collapsed by ``--tool-search`` (the transform filters ``tools/list`` only),
    so on a large set they were context cost that search could not hide.
    """
    resolved = _response_schemas_by_route(resolve_internal_refs(spec))
    # Leave schema references for fastmcp; inline the rest. See the docstring.
    spec_for_fastmcp = resolve_internal_refs(spec, skip_prefixes=(SCHEMA_REF_PREFIX,))

    def enrich_component(route: Any, component: Any) -> None:
        responses = route.responses or {}
        by_code = resolved.get((route.path, str(route.method).upper()))
        if responses and by_code:
            # Rebuild the mapping with resolved schemas instead of mutating
            # fastmcp's own parsed objects, which are shared with the route.
            responses = {
                code: (
                    info.model_copy(update={"content_schema": by_code[str(code)]})
                    if str(code) in by_code
                    else info
                )
                for code, info in responses.items()
            }
        component.description = format_description_with_responses(
            component.description or "",
            responses,
            getattr(route, "parameters", None),
            getattr(route, "request_body", None),
        )

    logger.debug(f"Building MCP server '{name}' for API base URL: {base_url}")
    return FastMCP.from_openapi(
        openapi_spec=spec_for_fastmcp,
        client=httpx2.AsyncClient(base_url=base_url, timeout=timeout),
        name=name,
        mcp_component_fn=enrich_component,
        validate_output=validate_output,
    )
