"""
Tests for serving APIs straight from a spec URL or local file (``--spec_url``).

The specs here are written to temporary files, so nothing touches the network:
loading a spec and building tools from it make no HTTP calls.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import httpx2
import pytest
from fastmcp import FastMCP
from fastmcp.tools import Tool

from smartapi_mcp import server
from smartapi_mcp.config import load_config
from smartapi_mcp.openapi import SpecError, _local_spec_path, fetch_spec

DRAFT_YAML = """\
openapi: 3.0.0
info:
  title: Draft API
  version: "0.1"
servers:
  - url: https://draft.example.com
paths:
  /thing/{id}:
    get:
      operationId: getThing
      summary: Get a thing by id
      parameters:
        - name: id
          in: path
          required: true
          schema: {type: string}
      responses:
        "200": {description: OK}
"""


@pytest.fixture
def draft_spec(tmp_path):
    path = tmp_path / "draft.yaml"
    path.write_text(DRAFT_YAML)
    return path


async def tool_names(mcp: FastMCP) -> set[str]:
    return {tool.name for tool in await mcp.list_tools()}


class TestLocalSpecPath:
    @pytest.mark.parametrize(
        ("url", "expected"),
        [
            ("specs/draft.yaml", "specs/draft.yaml"),
            ("/abs/draft.yaml", "/abs/draft.yaml"),
            ("file:///abs/my%20draft.yaml", "/abs/my draft.yaml"),
            (r"C:\specs\draft.yaml", r"C:\specs\draft.yaml"),
        ],
    )
    def test_files_are_recognised(self, url, expected):
        assert str(_local_spec_path(url)) == expected

    @pytest.mark.parametrize(
        "url", ["https://example.com/spec.yaml", "http://localhost:8000/openapi.json"]
    )
    def test_remote_urls_are_not_files(self, url):
        assert _local_spec_path(url) is None


class TestFetchLocalSpec:
    def test_reads_a_yaml_file(self, draft_spec):
        assert fetch_spec(str(draft_spec))["info"]["title"] == "Draft API"

    def test_reads_a_file_url(self, draft_spec):
        assert fetch_spec(draft_spec.as_uri())["info"]["title"] == "Draft API"

    def test_reads_json(self, tmp_path):
        path = tmp_path / "spec.json"
        path.write_text(
            json.dumps({"openapi": "3.0.0", "info": {"title": "J"}, "paths": {}})
        )
        assert fetch_spec(str(path))["info"]["title"] == "J"

    def test_edits_are_picked_up(self, draft_spec):
        """Files are never cached, so a draft can be edited between loads."""
        assert fetch_spec(str(draft_spec))["info"]["title"] == "Draft API"
        draft_spec.write_text(DRAFT_YAML.replace("Draft API", "Edited API"))
        assert fetch_spec(str(draft_spec))["info"]["title"] == "Edited API"

    def test_does_not_touch_the_network(self, draft_spec):
        with patch.object(httpx2, "Client", side_effect=AssertionError("network")):
            fetch_spec(str(draft_spec))

    def test_a_missing_file_is_a_spec_error(self, tmp_path):
        with pytest.raises(SpecError, match="Cannot read spec file"):
            fetch_spec(str(tmp_path / "nope.yaml"))

    def test_external_refs_are_still_refused(self, tmp_path):
        path = tmp_path / "refs.yaml"
        path.write_text(
            DRAFT_YAML.replace(
                '"200": {description: OK}', '"200": {$ref: "common.yaml#/ok"}'
            )
        )
        with pytest.raises(SpecError, match="external"):
            fetch_spec(str(path))


class TestBuildSpecUrlServers:
    async def test_builds_one_server_per_spec(self, draft_spec):
        (built,) = await server.build_spec_url_servers([str(draft_spec)])
        assert built.name == "Draft API"
        assert await tool_names(built) == {"getThing"}

    async def test_a_bad_spec_is_an_error_not_a_skip(self, tmp_path):
        with pytest.raises(ValueError, match=r"Cannot serve the spec at .*nope\.yaml"):
            await server.build_spec_url_servers([str(tmp_path / "nope.yaml")])

    async def test_an_unresolvable_server_url_is_an_error(self, tmp_path):
        path = tmp_path / "noservers.yaml"
        path.write_text(
            DRAFT_YAML.replace("servers:\n  - url: https://draft.example.com\n", "")
        )
        with pytest.raises(ValueError, match="declares no servers"):
            await server.build_spec_url_servers([str(path)])

    async def test_a_spec_with_no_operations_is_an_error(self, tmp_path):
        path = tmp_path / "empty.yaml"
        path.write_text(
            "openapi: 3.0.0\ninfo: {title: Empty, version: '1'}\n"
            "servers: [{url: 'https://x.example.com'}]\npaths: {}\n"
        )
        with pytest.raises(ValueError, match="produced no tools"):
            await server.build_spec_url_servers([str(path)])


class TestBuildServerForSet:
    async def test_spec_urls_alone_need_no_registry(self, draft_spec):
        with patch.object(
            server, "build_registry", side_effect=AssertionError("registry")
        ):
            mcp = await server.build_server_for_set(
                spec_urls=[str(draft_spec)], server_name="test", tool_search="off"
            )
        assert mcp.name == "test"
        assert await tool_names(mcp) == {"draft_api_getThing"}

    async def test_spec_urls_are_added_to_a_registry_selection(self, draft_spec):
        registry_server = FastMCP("registry")

        @registry_server.tool
        def mygene_query(q: str) -> str:
            return q

        async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
            return {}

        async def fake_merged(smartapi_ids, server_name="smartapi_mcp"):  # noqa: ARG001
            return registry_server

        with (
            patch.object(server, "build_registry", fake_build_registry),
            patch.object(server, "get_merged_mcp_server", fake_merged),
        ):
            mcp = await server.build_server_for_set(
                smartapi_ids=["abc"], spec_urls=[str(draft_spec)], tool_search="off"
            )
        assert await tool_names(mcp) == {"mygene_query", "draft_api_getThing"}

    async def test_spec_url_tools_stay_listed_under_tool_search(self, draft_spec):
        """A 20-tool registry selection collapses; the draft's tool does not."""
        registry_server = FastMCP("registry")
        for i in range(20):
            registry_server.add_tool(
                Tool.from_function(lambda q="": q, name=f"api_{i}", description="d")
            )

        async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
            return {}

        async def fake_merged(smartapi_ids, server_name="smartapi_mcp"):  # noqa: ARG001
            return registry_server

        with (
            patch.object(server, "build_registry", fake_build_registry),
            patch.object(server, "get_merged_mcp_server", fake_merged),
        ):
            mcp = await server.build_server_for_set(
                smartapi_ids=["abc"], spec_urls=[str(draft_spec)]
            )
        listed = await tool_names(mcp)
        assert {"search_tools", "call_tool", "draft_api_getThing"} <= listed
        assert "api_0" not in listed
        search = next(t for t in await mcp.list_tools() if t.name == "search_tools")
        assert "20 additional tools" in (search.description or "")
        assert "BioThings" not in (search.description or "")

    async def test_a_bad_spec_fails_before_the_registry_is_queried(self, tmp_path):
        with (
            patch.object(
                server, "build_registry", side_effect=AssertionError("registry")
            ),
            pytest.raises(ValueError, match="Cannot serve the spec"),
        ):
            await server.build_server_for_set(
                api_set="biothings_core", spec_urls=[str(tmp_path / "nope.yaml")]
            )

    async def test_nothing_selected_still_raises(self):
        with pytest.raises(ValueError, match="No SmartAPI IDs"):
            await server.build_server_for_set()


class TestConfig:
    def test_env_var_is_comma_separated(self, monkeypatch):
        monkeypatch.setenv("SMARTAPI_SPEC_URLS", "a.yaml, https://x/b.json,")
        assert load_config().spec_urls == ["a.yaml", "https://x/b.json"]

    def test_flag_is_repeatable_and_comma_separated(self):
        args = SimpleNamespace(spec_url=["a.yaml", "b.yaml,c.yaml"])
        assert load_config(args).spec_urls == ["a.yaml", "b.yaml", "c.yaml"]

    def test_flag_overrides_env(self, monkeypatch):
        monkeypatch.setenv("SMARTAPI_SPEC_URLS", "env.yaml")

        args = SimpleNamespace(spec_url=["cli.yaml"])
        assert load_config(args).spec_urls == ["cli.yaml"]
