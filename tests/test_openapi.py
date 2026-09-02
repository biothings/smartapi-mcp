"""
Tests for smartapi_mcp.openapi

This module replaced ``awslabs.openapi_mcp_server``'s spec loader, validator and
server builder. Everything here is offline: HTTP is served by an
``httpx2.MockTransport`` so the retry, cache and size-cap paths are exercised
without touching the SmartAPI registry.
"""

import json
from unittest.mock import patch

import httpx2
import pytest
from fastmcp import FastMCP

from smartapi_mcp import openapi as mod
from smartapi_mcp.openapi import (
    MAX_SPEC_BYTES,
    SPEC_FETCH_ATTEMPTS,
    SpecError,
    build_openapi_server,
    clear_spec_cache,
    fetch_spec,
    reject_external_refs,
    resolve_internal_refs,
    validate_spec,
)

MINIMAL_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Test API", "version": "1.0"},
    "paths": {},
}

# A spec whose response is a $ref, which is the case that needs resolving: the
# formatter can only document "Response Item Properties" if it can see them.
REF_SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Ref API", "version": "1.0"},
    "paths": {
        "/thing": {
            "get": {
                "summary": "Get a thing",
                "responses": {
                    "200": {
                        "description": "OK",
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/Thing"}
                            }
                        },
                    }
                },
            }
        }
    },
    "components": {
        "schemas": {
            "Thing": {
                "type": "object",
                "properties": {
                    "widget_id": {"type": "string", "description": "the widget id"},
                    "widget_size": {"type": "integer", "description": "how big"},
                },
            }
        }
    },
    "servers": [{"url": "https://api.example.com"}],
}


@pytest.fixture(autouse=True)
def _clear_cache():
    clear_spec_cache()
    yield
    clear_spec_cache()


# Captured before any patching, so the factory below builds a real client
# rather than re-entering the patched name.
_REAL_CLIENT = httpx2.Client


def mock_client(handler):
    """Return a factory that swaps httpx2.Client's transport for ``handler``."""

    def factory(**kwargs):
        kwargs.pop("follow_redirects", None)
        return _REAL_CLIENT(transport=httpx2.MockTransport(handler), **kwargs)

    return factory


class TestValidateSpec:
    def test_accepts_a_minimal_openapi_3_document(self):
        assert validate_spec(MINIMAL_SPEC) is MINIMAL_SPEC

    @pytest.mark.parametrize("bad", [[], "openapi", 42, None])
    def test_rejects_a_non_mapping_root(self, bad):
        with pytest.raises(SpecError, match="must be a mapping"):
            validate_spec(bad)

    @pytest.mark.parametrize("missing", ["openapi", "info", "paths"])
    def test_rejects_a_missing_required_field(self, missing):
        spec = {k: v for k, v in MINIMAL_SPEC.items() if k != missing}
        with pytest.raises(SpecError, match=f"missing the required '{missing}'"):
            validate_spec(spec)

    def test_warns_but_accepts_a_non_3x_version(self):
        """Refusing would drop an API that may still work; warn instead."""
        spec = {**MINIMAL_SPEC, "openapi": "2.0"}
        with patch.object(mod, "logger") as mock_logger:
            assert validate_spec(spec) is spec
        assert "2.0" in mock_logger.warning.call_args[0][0]


class TestRejectExternalRefs:
    def test_internal_refs_are_allowed(self):
        reject_external_refs(REF_SPEC)  # does not raise

    @pytest.mark.parametrize(
        "ref",
        [
            "https://evil.example.com/schema.json",
            "http://169.254.169.254/latest/meta-data/",
            "file:///etc/passwd",
            "./sibling.yaml#/components/schemas/Thing",
            "common.yaml",
        ],
    )
    def test_external_refs_are_refused(self, ref):
        with pytest.raises(SpecError, match="Refusing to resolve external"):
            reject_external_refs({"components": {"schemas": {"X": {"$ref": ref}}}})

    def test_refs_nested_in_lists_are_found(self):
        node = {"allOf": [{"type": "object"}, {"$ref": "http://x.example/y"}]}
        with pytest.raises(SpecError, match="Refusing to resolve external"):
            reject_external_refs(node)

    def test_a_ref_that_is_not_a_string_is_ignored(self):
        """A key named $ref holding a non-string is not a reference."""
        reject_external_refs({"$ref": {"nested": "value"}})


class TestResolveInternalRefs:
    def test_inlines_a_reference(self):
        out = resolve_internal_refs(REF_SPEC)
        schema = out["paths"]["/thing"]["get"]["responses"]["200"]["content"][
            "application/json"
        ]["schema"]
        assert schema["type"] == "object"
        assert "widget_id" in schema["properties"]

    def test_does_not_modify_the_input(self):
        before = json.dumps(REF_SPEC, sort_keys=True)
        resolve_internal_refs(REF_SPEC)
        assert json.dumps(REF_SPEC, sort_keys=True) == before

    def test_sibling_keys_override_the_target(self):
        """Per JSON Schema, keys alongside a $ref win over the referenced one."""
        spec = {
            "a": {"$ref": "#/defs/x", "description": "overridden"},
            "defs": {"x": {"type": "string", "description": "original"}},
        }
        out = resolve_internal_refs(spec)
        assert out["a"] == {"type": "string", "description": "overridden"}

    def test_a_self_referential_schema_terminates(self):
        """TRAPI's Attribute contains a list of Attribute; this must not loop."""
        spec = {
            "root": {"$ref": "#/defs/Node"},
            "defs": {
                "Node": {
                    "type": "object",
                    "properties": {"children": {"$ref": "#/defs/Node"}},
                }
            },
        }
        out = resolve_internal_refs(spec)
        assert out["root"]["type"] == "object"
        # The recursive branch is cut to an empty schema rather than expanded.
        assert out["root"]["properties"]["children"] == {}

    def test_mutually_recursive_schemas_terminate(self):
        spec = {
            "root": {"$ref": "#/defs/A"},
            "defs": {
                "A": {"type": "object", "properties": {"b": {"$ref": "#/defs/B"}}},
                "B": {"type": "object", "properties": {"a": {"$ref": "#/defs/A"}}},
            },
        }
        out = resolve_internal_refs(spec)
        assert out["root"]["properties"]["b"]["type"] == "object"

    def test_max_depth_stops_expansion(self):
        spec = {
            "root": {"$ref": "#/defs/L0"},
            "defs": {
                "L0": {"next": {"$ref": "#/defs/L1"}},
                "L1": {"next": {"$ref": "#/defs/L2"}},
                "L2": {"leaf": True},
            },
        }
        assert resolve_internal_refs(spec, max_depth=1)["root"]["next"] == {}
        deep = resolve_internal_refs(spec, max_depth=5)
        assert deep["root"]["next"]["next"] == {"leaf": True}

    def test_a_dangling_ref_is_left_in_place(self):
        """A partly-documented description beats refusing to build the server."""
        spec = {"a": {"$ref": "#/defs/missing"}, "defs": {}}
        assert resolve_internal_refs(spec)["a"] == {"$ref": "#/defs/missing"}

    def test_external_refs_are_left_alone(self):
        """reject_external_refs is the gate for these; the resolver ignores them."""
        spec = {"a": {"$ref": "https://x.example/y"}}
        assert resolve_internal_refs(spec)["a"] == {"$ref": "https://x.example/y"}

    def test_json_pointer_escapes_are_decoded(self):
        """~1 is '/' and ~0 is '~', and the order of replacement matters."""
        spec = {
            "a": {"$ref": "#/paths/~1thing~1{id}"},
            "paths": {"/thing/{id}": {"ok": True}},
        }
        assert resolve_internal_refs(spec)["a"] == {"ok": True}

    def test_array_indices_in_pointers_resolve(self):
        spec = {"a": {"$ref": "#/list/1"}, "list": [{"n": 0}, {"n": 1}]}
        assert resolve_internal_refs(spec)["a"] == {"n": 1}


class TestFetchSpec:
    def test_requires_a_url(self):
        with pytest.raises(SpecError, match="spec URL is required"):
            fetch_spec("")

    def test_fetches_parses_and_validates(self):
        def handler(_request):
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with patch.object(httpx2, "Client", mock_client(handler)):
            assert fetch_spec("https://example.com/spec") == MINIMAL_SPEC

    def test_caches_by_url(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with patch.object(httpx2, "Client", mock_client(handler)):
            fetch_spec("https://example.com/spec")
            fetch_spec("https://example.com/spec")
        assert len(calls) == 1

    def test_cache_can_be_bypassed(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with patch.object(httpx2, "Client", mock_client(handler)):
            fetch_spec("https://example.com/spec", use_cache=False)
            fetch_spec("https://example.com/spec", use_cache=False)
        assert len(calls) == 2

    def test_a_stale_cache_entry_is_refetched(self):
        calls = []

        def handler(request):
            calls.append(str(request.url))
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            patch.object(mod, "SPEC_CACHE_TTL", -1),
        ):
            fetch_spec("https://example.com/spec")
            fetch_spec("https://example.com/spec")
        assert len(calls) == 2

    def test_retries_a_server_error_then_succeeds(self):
        calls = []

        def handler(_request):
            calls.append(1)
            if len(calls) < SPEC_FETCH_ATTEMPTS:
                return httpx2.Response(503)
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            patch.object(mod.time, "sleep"),
        ):
            assert fetch_spec("https://example.com/spec") == MINIMAL_SPEC
        assert len(calls) == SPEC_FETCH_ATTEMPTS

    def test_gives_up_after_the_attempt_limit(self):
        calls = []

        def handler(_request):
            calls.append(1)
            return httpx2.Response(503)

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            patch.object(mod.time, "sleep"),
            pytest.raises(httpx2.HTTPStatusError),
        ):
            fetch_spec("https://example.com/spec")
        assert len(calls) == SPEC_FETCH_ATTEMPTS

    def test_a_client_error_is_not_retried(self):
        """An unknown SmartAPI id 404s on every attempt; backoff is wasted."""
        calls = []

        def handler(_request):
            calls.append(1)
            return httpx2.Response(404)

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            pytest.raises(httpx2.HTTPStatusError),
        ):
            fetch_spec("https://example.com/spec")
        assert len(calls) == 1

    def test_retries_a_transport_error(self):
        calls = []

        def handler(request):
            calls.append(1)
            if len(calls) < 2:
                err_msg = "connection refused"
                raise httpx2.ConnectError(err_msg, request=request)
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            patch.object(mod.time, "sleep"),
        ):
            assert fetch_spec("https://example.com/spec") == MINIMAL_SPEC
        assert len(calls) == 2

    def test_refuses_an_oversized_spec(self):
        def handler(_request):
            return httpx2.Response(200, content=b"x" * (MAX_SPEC_BYTES + 1))

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            pytest.raises(SpecError, match="Spec too large"),
        ):
            fetch_spec("https://example.com/spec")

    def test_refuses_a_spec_carrying_an_external_ref(self):
        spec = {
            **MINIMAL_SPEC,
            "components": {"schemas": {"X": {"$ref": "file:///etc/passwd"}}},
        }

        def handler(_request):
            return httpx2.Response(200, json=spec)

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            pytest.raises(SpecError, match="Refusing to resolve external"),
        ):
            fetch_spec("https://example.com/spec")

    def test_a_failed_fetch_is_not_cached(self):
        state = {"fail": True}

        def handler(_request):
            if state["fail"]:
                return httpx2.Response(404)
            return httpx2.Response(200, json=MINIMAL_SPEC)

        with patch.object(httpx2, "Client", mock_client(handler)):
            with pytest.raises(httpx2.HTTPStatusError):
                fetch_spec("https://example.com/spec")
            state["fail"] = False
            assert fetch_spec("https://example.com/spec") == MINIMAL_SPEC


class TestParsing:
    def test_yaml_is_accepted_when_pyyaml_is_available(self):
        pytest.importorskip("yaml")
        body = b"openapi: '3.0.0'\ninfo:\n  title: Y\npaths: {}\n"

        def handler(_request):
            return httpx2.Response(200, content=body)

        with patch.object(httpx2, "Client", mock_client(handler)):
            assert fetch_spec("https://example.com/spec")["info"]["title"] == "Y"

    def test_unparseable_content_raises(self):
        def handler(_request):
            return httpx2.Response(200, content=b"\x00not json or yaml: [")

        with (
            patch.object(httpx2, "Client", mock_client(handler)),
            pytest.raises(SpecError),
        ):
            fetch_spec("https://example.com/spec")


class TestBuildOpenapiServer:
    @pytest.mark.asyncio
    async def test_every_operation_becomes_a_tool(self):
        """fastmcp 3 maps all routes to tools, so no route_maps are needed.

        The awslabs wrapper passed route maps forcing GET-with-query-params to
        MCPType.TOOL; this asserts that is now redundant rather than load-bearing.
        """
        server = build_openapi_server(REF_SPEC, "https://api.example.com", "Ref API")
        tools = await server.list_tools()
        assert len(tools) == 1
        assert await server.list_resource_templates() == []
        assert await server.list_resources() == []

    @pytest.mark.asyncio
    async def test_name_becomes_the_server_name(self):
        """_merge_servers_into derives the per-API tool prefix from this."""
        server = build_openapi_server(REF_SPEC, "https://api.example.com", "Ref API")
        assert server.name == "Ref API"

    @pytest.mark.asyncio
    async def test_no_prompts_are_generated(self):
        """Dropped deliberately: prompts restated their tool and, unlike tools,
        are not collapsed by the --tool-search transform."""
        spec = {
            **REF_SPEC,
            "paths": {
                "/thing": {
                    "get": {
                        "operationId": "getThing",
                        "summary": "Get a thing",
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        server = build_openapi_server(spec, "https://api.example.com", "Ref API")
        assert await server.list_prompts() == []

    @pytest.mark.asyncio
    async def test_response_refs_are_documented_in_the_description(self):
        """The reason resolve_internal_refs exists.

        fastmcp resolves refs for input schemas but leaves them in the response
        schemas it hands to the description formatter, so without resolution an
        operation returning a $ref is documented as returning nothing specific.
        """
        server = build_openapi_server(REF_SPEC, "https://api.example.com", "Ref API")
        description = (await server.list_tools())[0].description or ""
        assert "widget_id" in description
        assert "the widget id" in description

    @pytest.mark.asyncio
    async def test_a_recursive_schema_stays_behind_defs(self):
        """Why the resolved spec must not be the one handed to fastmcp.

        A self-referencing schema cannot be inlined -- it has no finite
        expansion -- so fastmcp represents it with ``$defs`` plus internal
        references. Pre-resolving the whole spec destroys that structure: the
        recursive branch gets cut to an empty schema, and on a real TRAPI API
        this inflated one tool's input schema from 67 KB to 115 KB while losing
        the recursion. So ``build_openapi_server`` passes the pristine spec to
        fastmcp and keeps the resolved copy for descriptions only.
        """
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Recursive API", "version": "1.0"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/a": {
                    "post": {
                        "requestBody": {
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Node"}
                                }
                            }
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            "components": {
                "schemas": {
                    "Node": {
                        "type": "object",
                        "properties": {
                            "label": {"type": "string"},
                            "children": {
                                "type": "array",
                                "items": {"$ref": "#/components/schemas/Node"},
                            },
                        },
                    }
                }
            },
        }
        server = build_openapi_server(spec, "https://api.example.com", "Recursive API")
        schema = (await server.list_tools())[0].parameters
        # The recursion survives as a $defs entry referring to itself.
        assert "$defs" in schema
        assert "Node" in schema["$defs"]
        assert "$ref" in str(schema["$defs"]["Node"])

        # Pre-resolving instead would have flattened the recursion away, which
        # is exactly what build_openapi_server avoids doing: each level is
        # inlined until the cycle check cuts the next one to an empty schema.
        flattened = resolve_internal_refs(spec)
        node = flattened["components"]["schemas"]["Node"]
        inlined_child = node["properties"]["children"]["items"]
        assert inlined_child["type"] == "object"  # one level expanded...
        assert inlined_child["properties"]["children"]["items"] == {}  # ...then cut

    @pytest.mark.asyncio
    async def test_parameter_level_refs_are_inlined_for_fastmcp(self):
        """fastmcp ignores $refs at the parameter object level, dropping them.

        Regression test. fastmcp resolves references inside *schemas* but not a
        ``$ref`` standing in for a whole Parameter Object, so a spec written
        that way arrived with an empty schema for that parameter -- measured on
        MyTaxon.info, whose ``callback`` parameter came through as ``{}``. The
        awslabs loader happened to avoid this by pre-resolving everything with
        prance. build_openapi_server now inlines every internal $ref *except*
        schema ones before handing the spec over.
        """
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Param Ref API", "version": "1.0"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/thing": {
                    "get": {
                        "parameters": [{"$ref": "#/components/parameters/callback"}],
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
            "components": {
                "parameters": {
                    "callback": {
                        "name": "callback",
                        "in": "query",
                        "description": "make a JSONP call",
                        "schema": {"type": "string"},
                    }
                }
            },
        }
        server = build_openapi_server(spec, "https://api.example.com", "Param Ref API")
        schema = (await server.list_tools())[0].parameters
        callback = schema["properties"]["callback"]
        assert callback.get("type") == "string"
        assert "JSONP" in callback.get("description", "")

    def test_skip_prefixes_leaves_matching_refs_alone(self):
        spec = {
            "a": {"$ref": "#/components/schemas/X"},
            "b": {"$ref": "#/components/parameters/Y"},
            "components": {
                "schemas": {"X": {"type": "string"}},
                "parameters": {"Y": {"name": "y", "in": "query"}},
            },
        }
        out = resolve_internal_refs(spec, skip_prefixes=("#/components/schemas/",))
        assert out["a"] == {"$ref": "#/components/schemas/X"}
        assert out["b"] == {"name": "y", "in": "query"}

    @pytest.mark.asyncio
    async def test_request_body_is_sent_nested_even_though_the_schema_is_flat(self):
        """fastmcp 4 hoists request-body fields into top-level tool parameters.

        In fastmcp 3 a body arrived as a single nested object parameter (the
        TRAPI APIs showed one ``request`` property); 4.x names each field
        individually, which is easier for a model to fill in. The wire format
        must not change with it -- the API still expects the nested JSON -- so
        this pins both halves: flat parameters in, nested body out.
        """
        spec = {
            "openapi": "3.0.0",
            "info": {"title": "Body API", "version": "1.0"},
            "servers": [{"url": "https://api.example.com"}],
            "paths": {
                "/query": {
                    "post": {
                        "requestBody": {
                            "required": True,
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "message": {
                                                "type": "object",
                                                "properties": {"q": {"type": "string"}},
                                            },
                                            "log_level": {"type": "string"},
                                        },
                                        "required": ["message"],
                                    }
                                }
                            },
                        },
                        "responses": {"200": {"description": "OK"}},
                    }
                }
            },
        }
        captured = {}

        def handler(request):
            captured["body"] = json.loads(request.content or b"{}")
            return httpx2.Response(200, json={"ok": True})

        server = FastMCP.from_openapi(
            openapi_spec=spec,
            client=httpx2.AsyncClient(
                base_url="https://api.example.com",
                transport=httpx2.MockTransport(handler),
            ),
            name="Body API",
        )
        tool = (await server.list_tools())[0]
        # The body's fields are separate parameters, not one nested object.
        assert sorted(tool.parameters["properties"]) == ["log_level", "message"]

        await server.call_tool(
            tool.name, {"message": {"q": "hello"}, "log_level": "DEBUG"}
        )
        assert captured["body"] == {"message": {"q": "hello"}, "log_level": "DEBUG"}
