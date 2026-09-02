"""Tests for the BioThings generic-facade module and the server dispatcher."""

from unittest.mock import patch

import pytest
from fastmcp import FastMCP
from fastmcp.client import Client

from smartapi_mcp import server
from smartapi_mcp.biothings import (
    CORE_API_BOOST,
    BioThingsAPIEntry,
    analyze_biothings_spec,
    build_biothings_facade,
    build_registry_from_entries,
    is_biothings_family,
    is_biothings_registry,
    partition_biothings,
    rank_apis,
)
from smartapi_mcp.smartapi import CORE_BIOTHINGS_API_IDS


# --------------------------------------------------------------------------- #
# HTTP / spec mocking helpers
# --------------------------------------------------------------------------- #
class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    """Async-context-manager stand-in for httpx.AsyncClient that records calls."""

    def __init__(self, recorder, payload):
        self._recorder = recorder
        self._payload = payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def request(self, method, url, **kwargs):
        self._recorder.append((method, url, kwargs))
        return _FakeResponse(self._payload)


_MYGENE_SPEC = {
    "info": {"title": "MyGene.info API"},
    "servers": [{"url": "https://mygene.info/v3"}],
    "paths": {"/gene/{geneid}": {}, "/query": {}, "/metadata/fields": {}},
}

# A fully-standard BioThings spec (all six common operations, single entity).
_STANDARD_SPEC = {
    "info": {"title": "MyGene.info API"},
    "servers": [{"url": "https://mygene.info/v3"}],
    "paths": {
        "/gene/{geneid}": {"get": {}},
        "/gene": {"post": {}},
        "/query": {"get": {}, "post": {}},
        "/metadata": {"get": {}},
        "/metadata/fields": {"get": {}},
    },
}

# Same, plus an extra non-standard endpoint (a second entity type).
_EXTRA_SPEC = {
    "info": {"title": "MyChem.info API"},
    "servers": [{"url": "https://mychem.info/v1"}],
    "paths": {
        "/chem/{id}": {"get": {}},
        "/chem": {"post": {}},
        "/query": {"get": {}, "post": {}},
        "/metadata": {"get": {}},
        "/metadata/fields": {"get": {}},
        "/drug/{id}": {"get": {}},  # extra endpoint beyond the standard set
    },
}


def _sample_registry():
    return {
        "mygene": BioThingsAPIEntry(
            "mygene",
            "59d",
            "MyGene.info API",
            "gene annotation service",
            ["gene", "biothings"],
        ),
        "mydisease": BioThingsAPIEntry(
            "mydisease",
            "671",
            "MyDisease.info API",
            "disease annotation and ontology lookups",
            ["disease", "biothings"],
        ),
    }


# --------------------------------------------------------------------------- #
# Registry / ranking
# --------------------------------------------------------------------------- #
def test_build_registry_from_entries_slugifies_and_dedupes():
    entries = [
        {"_id": "1", "title": "MyGene.info API", "description": "", "tags": []},
        {"_id": "2", "title": "MyGene.info API", "description": "", "tags": []},
        {"_id": "", "title": "skipped", "description": "", "tags": []},
    ]
    registry = build_registry_from_entries(entries)
    assert set(registry) == {"mygene", "mygene_2"}
    assert registry["mygene"].smartapi_id == "1"
    assert registry["mygene_2"].smartapi_id == "2"


def test_is_biothings_registry():
    assert is_biothings_registry(_sample_registry()) is True
    assert is_biothings_registry({}) is False
    mixed = _sample_registry()
    mixed["other"] = BioThingsAPIEntry("other", "x", tags=["translator"])
    assert is_biothings_registry(mixed) is False


def test_rank_apis_keyword_ranks_relevant_first():
    ranked = rank_apis(_sample_registry(), "disease")
    assert ranked[0]["name"] == "mydisease"
    assert all("score" in entry for entry in ranked)


def test_rank_apis_no_keyword_returns_full_catalog_sorted():
    ranked = rank_apis(_sample_registry())
    assert [entry["name"] for entry in ranked] == ["mydisease", "mygene"]


def test_rank_apis_truncates_long_descriptions():
    registry = {
        "x": BioThingsAPIEntry("x", "1", "X", "d" * 500, ["biothings"]),
    }
    ranked = rank_apis(registry)
    assert ranked[0]["description"].endswith("...")
    assert len(ranked[0]["description"]) <= 203


# --------------------------------------------------------------------------- #
# Spec classification (catching APIs with extra endpoints)
# --------------------------------------------------------------------------- #
def test_analyze_standard_spec_has_no_extra_ops():
    base_url, biothing_type, extra = analyze_biothings_spec(_STANDARD_SPEC)
    assert base_url == "https://mygene.info/v3"
    assert biothing_type == "gene"
    assert extra == []


def test_analyze_spec_detects_extra_endpoint():
    _, biothing_type, extra = analyze_biothings_spec(_EXTRA_SPEC)
    assert biothing_type == "chem"
    assert ("GET", "/drug/{}") in extra


def test_analyze_spec_without_entity_type_is_all_extra():
    spec = {
        "info": {"title": "Some API"},
        "servers": [{"url": "https://x.example"}],
        "paths": {"/query": {"get": {}}, "/metakg": {"get": {}}},
    }
    _, biothing_type, extra = analyze_biothings_spec(spec)
    assert biothing_type is None
    assert ("GET", "/metakg") in extra


async def test_partition_biothings_splits_standard_from_extra():
    entries = {
        "mygene": BioThingsAPIEntry("mygene", "g", tags=["biothings"]),
        "mychem": BioThingsAPIEntry("mychem", "c", tags=["biothings"]),
    }
    specs = {"g": _STANDARD_SPEC, "c": _EXTRA_SPEC}

    with patch(
        "smartapi_mcp.biothings.load_api_spec", side_effect=lambda sid: specs[sid]
    ):
        facade_entries, extra_ids = await partition_biothings(entries)

    assert set(facade_entries) == {"mygene"}
    assert extra_ids == ["c"]
    # facade-eligible entry got its endpoints cached
    assert facade_entries["mygene"].base_url == "https://mygene.info/v3"
    assert facade_entries["mygene"].biothing_type == "gene"


async def test_partition_biothings_treats_unloadable_spec_as_per_api():
    entries = {"broken": BioThingsAPIEntry("broken", "b", tags=["biothings"])}

    def _raise(_sid):
        msg = "boom"
        raise RuntimeError(msg)

    with patch("smartapi_mcp.biothings.load_api_spec", side_effect=_raise):
        facade_entries, extra_ids = await partition_biothings(entries)

    assert facade_entries == {}
    assert extra_ids == ["b"]


# --------------------------------------------------------------------------- #
# Facade structure
# --------------------------------------------------------------------------- #
async def test_facade_exposes_exactly_five_tools():
    server_obj = build_biothings_facade(_sample_registry(), "test")
    async with Client(server_obj) as client:
        names = sorted(tool.name for tool in await client.list_tools())
    assert names == [
        "biothings_fields",
        "biothings_get",
        "biothings_getbatch",
        "biothings_query",
        "list_biothings_apis",
    ]


async def test_facade_lists_valid_api_names_in_description():
    server_obj = build_biothings_facade(_sample_registry(), "test")
    async with Client(server_obj) as client:
        tools = {t.name: t for t in await client.list_tools()}
    assert "mygene" in tools["biothings_query"].description
    assert "mydisease" in tools["biothings_query"].description


async def test_list_biothings_apis_returns_data_not_tools():
    server_obj = build_biothings_facade(_sample_registry(), "test")
    async with Client(server_obj) as client:
        result = await client.call_tool("list_biothings_apis", {"keyword": "disease"})
    payload = result.structured_content["result"]
    assert payload[0]["name"] == "mydisease"


# --------------------------------------------------------------------------- #
# Generic tools hit the right BioThings endpoints
# --------------------------------------------------------------------------- #
@pytest.fixture
def facade_with_recorder():
    recorder = []

    def _fake_client(*_args, **_kwargs):
        return _FakeClient(recorder, {"ok": True})

    with (
        patch("smartapi_mcp.biothings.load_api_spec", return_value=_MYGENE_SPEC),
        patch("smartapi_mcp.biothings.httpx.AsyncClient", side_effect=_fake_client),
    ):
        server_obj = build_biothings_facade(_sample_registry(), "test")
        yield server_obj, recorder


async def test_biothings_query_builds_correct_request(facade_with_recorder):
    server_obj, recorder = facade_with_recorder
    async with Client(server_obj) as client:
        await client.call_tool(
            "biothings_query", {"api": "mygene", "q": "CDK2", "size": 3}
        )
    method, url, kwargs = recorder[-1]
    assert method == "GET"
    assert url == "https://mygene.info/v3/query"
    assert kwargs["params"]["q"] == "CDK2"
    assert kwargs["params"]["size"] == 3


async def test_biothings_get_uses_biothing_type_path(facade_with_recorder):
    server_obj, recorder = facade_with_recorder
    async with Client(server_obj) as client:
        await client.call_tool("biothings_get", {"api": "mygene", "id": "1017"})
    method, url, _ = recorder[-1]
    assert method == "GET"
    assert url == "https://mygene.info/v3/gene/1017"


async def test_biothings_getbatch_posts_ids(facade_with_recorder):
    server_obj, recorder = facade_with_recorder
    async with Client(server_obj) as client:
        await client.call_tool(
            "biothings_getbatch", {"api": "mygene", "ids": ["1017", "1018"]}
        )
    method, url, kwargs = recorder[-1]
    assert method == "POST"
    assert url == "https://mygene.info/v3/gene"
    assert kwargs["data"]["ids"] == "1017,1018"


async def test_biothings_fields_hits_metadata_fields(facade_with_recorder):
    server_obj, recorder = facade_with_recorder
    async with Client(server_obj) as client:
        await client.call_tool("biothings_fields", {"api": "mygene"})
    method, url, _ = recorder[-1]
    assert method == "GET"
    assert url == "https://mygene.info/v3/metadata/fields"


async def test_unknown_api_raises(facade_with_recorder):
    server_obj, _ = facade_with_recorder
    async with Client(server_obj) as client:
        result = await client.call_tool(
            "biothings_query", {"api": "nope", "q": "x"}, raise_on_error=False
        )
    assert result.is_error
    assert "Unknown api" in str(result.content)


# --------------------------------------------------------------------------- #
# Dispatcher selection
# --------------------------------------------------------------------------- #
def _biothings_registry(n):
    return {
        f"a{i}": BioThingsAPIEntry(f"a{i}", str(i), f"API {i}", "", ["biothings"])
        for i in range(n)
    }


async def test_dispatcher_uses_facade_for_large_biothings_set():
    registry = _biothings_registry(10)

    async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
        return registry

    async def fake_partition(entries):
        return entries, []

    # A real (empty) FastMCP: build_server_for_set counts tools to decide
    # whether tool search applies, so an opaque object() is not a valid
    # server double. Empty means apply_tool_search early-returns, so the
    # identity assertions below still hold.
    sentinel = FastMCP("sentinel")
    with (
        patch.object(server, "build_registry", fake_build_registry),
        patch.object(server, "partition_biothings", fake_partition),
        patch.object(server, "build_biothings_facade", return_value=sentinel) as bf,
    ):
        result = await server.build_server_for_set(
            smartapi_ids=[str(i) for i in range(10)], facade_threshold=10
        )
    assert result is sentinel
    bf.assert_called_once()


async def test_dispatcher_uses_flat_for_small_set():
    registry = _biothings_registry(3)

    async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
        return registry

    flat = FastMCP("flat")
    captured = {}

    async def fake_merged(smartapi_ids, server_name="smartapi_mcp"):  # noqa: ARG001
        captured["ids"] = smartapi_ids
        return flat

    with (
        patch.object(server, "build_registry", fake_build_registry),
        patch.object(server, "get_merged_mcp_server", fake_merged),
    ):
        result = await server.build_server_for_set(
            smartapi_ids=["0", "1", "2"], facade_threshold=10
        )
    assert result is flat  # took the flat per-API path, not the facade
    assert captured["ids"] == ["0", "1", "2"]


async def test_dispatcher_hybrid_facade_plus_per_api_for_mixed_set():
    # A large mostly-BioThings set with one non-BioThings API (e.g. the SmartAPI
    # registry API) -> hybrid: facade over the BioThings subset, plus per-API
    # tools merged in for the non-BioThings API (nothing dropped).
    registry = _biothings_registry(10)
    registry["smartapi"] = BioThingsAPIEntry(
        "smartapi", "27a", "SmartAPI API", "", ["translator", "metakg"]
    )

    async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
        return registry

    captured = {}
    # A real (empty) FastMCP: build_server_for_set counts tools to decide
    # whether tool search applies, so an opaque object() is not a valid
    # server double. Empty means apply_tool_search early-returns, so the
    # identity assertions below still hold.
    facade_sentinel = FastMCP("facade_sentinel")

    def fake_facade(reg, name):  # noqa: ARG001
        captured["facade_names"] = set(reg)
        return facade_sentinel

    async def fake_get_mcp_server(smartapi_id):
        captured.setdefault("loaded", []).append(smartapi_id)
        return FastMCP("per_api")

    async def fake_merge(target, servers):
        captured["merge_target"] = target
        captured["merge_count"] = len(servers)
        return target

    async def fake_partition(entries):
        # All BioThings APIs are fully standard -> facade-eligible, no extras.
        return entries, []

    with (
        patch.object(server, "build_registry", fake_build_registry),
        patch.object(server, "partition_biothings", fake_partition),
        patch.object(server, "build_biothings_facade", fake_facade),
        patch.object(server, "get_mcp_server", fake_get_mcp_server),
        patch.object(server, "_merge_servers_into", fake_merge),
    ):
        result = await server.build_server_for_set(
            smartapi_ids=[str(i) for i in range(11)], facade_threshold=10
        )
    # Facade covers the BioThings subset only ...
    assert "smartapi" not in captured["facade_names"]
    assert len(captured["facade_names"]) == 10
    # ... and the non-BioThings API is loaded and merged into the same server.
    assert captured["loaded"] == ["27a"]
    assert captured["merge_count"] == 1
    assert captured["merge_target"] is facade_sentinel
    assert result is facade_sentinel


async def test_dispatcher_strict_routes_biothings_with_extra_endpoints_to_per_api():
    # With facade_strict=True, a BioThings API with extra endpoints is dropped
    # from the facade and served with faithful per-API tools instead.
    registry = _biothings_registry(10)  # names a0..a9, ids "0".."9"

    async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
        return registry

    captured = {}
    # A real (empty) FastMCP: build_server_for_set counts tools to decide
    # whether tool search applies, so an opaque object() is not a valid
    # server double. Empty means apply_tool_search early-returns, so the
    # identity assertions below still hold.
    facade_sentinel = FastMCP("facade_sentinel")

    def fake_facade(reg, name):  # noqa: ARG001
        captured["facade_names"] = set(reg)
        return facade_sentinel

    async def fake_partition(entries):
        # "a9" has extra endpoints -> per-API; the other 9 are facade-eligible.
        facade = {n: e for n, e in entries.items() if n != "a9"}
        return facade, ["9"]

    async def fake_get_mcp_server(smartapi_id):
        captured.setdefault("loaded", []).append(smartapi_id)
        return FastMCP("per_api")

    async def fake_merge(target, servers):
        captured["merge_count"] = len(servers)
        return target

    with (
        patch.object(server, "build_registry", fake_build_registry),
        patch.object(server, "partition_biothings", fake_partition),
        patch.object(server, "build_biothings_facade", fake_facade),
        patch.object(server, "get_mcp_server", fake_get_mcp_server),
        patch.object(server, "_merge_servers_into", fake_merge),
    ):
        result = await server.build_server_for_set(
            smartapi_ids=[str(i) for i in range(10)],
            facade_threshold=10,
            facade_strict=True,
        )
    assert result is facade_sentinel
    assert len(captured["facade_names"]) == 9
    assert "a9" not in captured["facade_names"]
    assert captured["loaded"] == ["9"]  # the extra-endpoint API served per-API
    assert captured["merge_count"] == 1


async def test_dispatcher_default_does_not_inspect_specs():
    # By default (facade_strict=False), specs are NOT inspected: all BioThings
    # APIs go straight into the facade and partition_biothings is never called.
    registry = _biothings_registry(10)

    async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
        return registry

    # A real (empty) FastMCP: build_server_for_set counts tools to decide
    # whether tool search applies, so an opaque object() is not a valid
    # server double. Empty means apply_tool_search early-returns, so the
    # identity assertions below still hold.
    facade_sentinel = FastMCP("facade_sentinel")
    with (
        patch.object(server, "build_registry", fake_build_registry),
        patch.object(server, "partition_biothings") as partition,
        patch.object(server, "build_biothings_facade", return_value=facade_sentinel),
    ):
        result = await server.build_server_for_set(
            smartapi_ids=[str(i) for i in range(10)], facade_threshold=10
        )
    assert result is facade_sentinel
    partition.assert_not_called()


async def test_dispatcher_pure_biothings_set_has_no_per_api_merge():
    registry = _biothings_registry(10)

    async def fake_build_registry(_ids, *, q=None):  # noqa: ARG001
        return registry

    # A real (empty) FastMCP: build_server_for_set counts tools to decide
    # whether tool search applies, so an opaque object() is not a valid
    # server double. Empty means apply_tool_search early-returns, so the
    # identity assertions below still hold.
    facade_sentinel = FastMCP("facade_sentinel")
    loaded = []

    async def fake_get_mcp_server(smartapi_id):
        loaded.append(smartapi_id)
        return FastMCP("per_api")

    async def fake_partition(entries):
        return entries, []

    with (
        patch.object(server, "build_registry", fake_build_registry),
        patch.object(server, "partition_biothings", fake_partition),
        patch.object(server, "build_biothings_facade", return_value=facade_sentinel),
        patch.object(server, "get_mcp_server", fake_get_mcp_server),
    ):
        result = await server.build_server_for_set(
            smartapi_ids=[str(i) for i in range(10)], facade_threshold=10
        )
    assert result is facade_sentinel
    assert loaded == []  # no per-API loading for an all-BioThings set


async def test_dispatcher_facade_off_forces_flat_even_when_large():
    flat = FastMCP("flat")

    async def fake_merged(smartapi_ids, server_name="smartapi_mcp"):  # noqa: ARG001
        return flat

    with (
        patch.object(server, "build_registry") as br,
        patch.object(server, "get_merged_mcp_server", fake_merged),
    ):
        result = await server.build_server_for_set(
            smartapi_ids=[str(i) for i in range(20)], facade="off"
        )
    assert result is flat
    br.assert_not_called()  # facade=off skips the registry build entirely


# --------------------------------------------------------------------------- #
# BioThings family membership (facade eligibility)
# --------------------------------------------------------------------------- #
def _entry(*tags):
    return BioThingsAPIEntry("x", "id", "X API", "desc", list(tags))


class TestIsBioThingsFamily:
    """Which APIs the generic facade may serve."""

    def test_biothings_tag_alone_qualifies(self):
        assert is_biothings_family(_entry("gene", "biothings")) is True

    def test_missing_biothings_tag_disqualifies(self):
        assert is_biothings_family(_entry("gene", "translator")) is False

    def test_trapi_tag_disqualifies_despite_biothings_tag(self):
        """TRAPI services are tagged biothings but are not annotation APIs.

        BioThings Explorer and Service Provider speak the Translator Reasoner
        query-graph protocol, so no generic facade tool applies to them. Left in
        the facade, the entity-type inference matches BTE's
        ``GET /asyncquery_status/{id}`` and ``biothings_get`` would return a job
        status as though it were an annotation record.
        """
        assert is_biothings_family(_entry("biothings", "trapi")) is False

    def test_tag_matching_is_case_and_space_insensitive(self):
        assert is_biothings_family(_entry("BioThings", " TRAPI ")) is False
        assert is_biothings_family(_entry(" BIOTHINGS ")) is True

    def test_no_tags_disqualifies(self):
        assert is_biothings_family(_entry()) is False

    def test_registry_predicate_agrees(self):
        assert is_biothings_registry({"a": _entry("biothings")}) is True
        assert is_biothings_registry({"a": _entry("biothings", "trapi")}) is False


class TestRankApis:
    """The facade's API discovery ranking."""

    def test_verbose_description_does_not_outrank_a_named_match(self):
        """Regression: the old scorer summed substring counts, rewarding prose.

        Searching "gene annotation" ranked MyGeneSet above MyGene because its
        longer description mentioned the terms more often. Term frequency is now
        binary and name/title hits are weighted, so the API named for the
        concept wins.
        """
        registry = {
            "mygene": BioThingsAPIEntry(
                "mygene",
                "1",
                "MyGene.info API",
                "gene annotation service",
                ["gene", "annotation", "biothings"],
            ),
            "mygeneset": BioThingsAPIEntry(
                "mygeneset",
                "2",
                "MyGeneSet.info API",
                "gene set gene gene annotation gene annotation collections of "
                "gene sets with gene annotation and gene annotation records",
                ["geneset", "biothings"],
            ),
        }
        ranked = [r["name"] for r in rank_apis(registry, "gene annotation")]
        assert ranked[0] == "mygene"

    def test_rare_terms_outweigh_common_ones(self):
        """IDF: a term shared by every API should not drive the ranking."""
        registry = {
            "common_a": BioThingsAPIEntry(
                "common_a", "1", "A API", "biothings annotation", ["biothings"]
            ),
            "ngd_api": BioThingsAPIEntry(
                "ngd_api",
                "2",
                "B API",
                "biothings annotation with ngd support",
                ["biothings"],
            ),
        }
        ranked = [r["name"] for r in rank_apis(registry, "biothings ngd")]
        assert ranked[0] == "ngd_api"

    def test_substring_matches_no_longer_count(self):
        """The old scorer matched "id" inside "identifier"/"candidate"."""
        registry = {
            "a": BioThingsAPIEntry("a", "1", "A", "identifier candidate provider", []),
        }
        assert rank_apis(registry, "id") == []

    def test_stopword_only_query_returns_the_full_catalog(self):
        """Nothing discriminating left, so don't return an arbitrary subset."""
        registry = _sample_registry()
        ranked = rank_apis(registry, "what data is there in the api")
        assert {r["name"] for r in ranked} == set(registry)

    def test_core_apis_are_preferred_among_matching_results(self):
        """A core API outranks a satellite when both match.

        Broad-coverage services carry the least distinctive vocabulary, so pure
        lexical scoring under-ranks exactly the APIs users most often want.
        """
        registry = {
            "mygene": BioThingsAPIEntry(
                "mygene",
                CORE_BIOTHINGS_API_IDS[0],
                "MyGene.info API",
                "gene annotation",
                ["gene", "biothings"],
            ),
            "satellite": BioThingsAPIEntry(
                "satellite",
                "not-a-core-id",
                "Satellite API",
                "gene annotation",
                ["gene", "biothings"],
            ),
        }
        ranked = [r["name"] for r in rank_apis(registry, "gene annotation")]
        assert ranked[0] == "mygene"

    def test_boost_does_not_promote_a_non_matching_core_api(self):
        """The boost is multiplicative, so a zero score stays zero."""
        registry = {
            "mygene": BioThingsAPIEntry(
                "mygene",
                CORE_BIOTHINGS_API_IDS[0],
                "MyGene.info API",
                "gene annotation",
                ["gene", "biothings"],
            ),
            "foodb": BioThingsAPIEntry(
                "foodb",
                "other-id",
                "FooDB API",
                "food composition and nutrient content",
                ["food", "biothings"],
            ),
        }
        ranked = [r["name"] for r in rank_apis(registry, "nutrient content")]
        assert ranked == ["foodb"], "a core API was promoted into an unrelated query"

    def test_boost_is_modest(self):
        """Guard the tuned value; see the rationale on the constant."""
        assert CORE_API_BOOST == 1.2

    def test_scores_are_reported(self):
        ranked = rank_apis(_sample_registry(), "disease")
        assert ranked
        assert ranked[0]["name"] == "mydisease"
        assert ranked[0]["score"] > 0
