"""
Tests for smartapi_mcp.config

``Config`` used to subclass the awslabs config dataclass, so these tests spent
most of their effort mocking that base class and the ``dataclasses.fields``
copy loop. With ``Config`` standalone, they assert real behaviour instead:
defaults, environment parsing, CLI precedence, and the malformed-value paths.
"""

import os
from dataclasses import fields, is_dataclass
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from smartapi_mcp.config import Config, load_config

# Every environment variable load_config reads. Cleared before each test so a
# developer's shell (or another test) cannot influence the result.
ENV_KEYS = (
    "SMARTAPI_ID",
    "SMARTAPI_IDS",
    "SMARTAPI_EXCLUDE_IDS",
    "SMARTAPI_Q",
    "SMARTAPI_API_SET",
    "SMARTAPI_FACADE",
    "FACADE_THRESHOLD",
    "FACADE_STRICT",
    "SMARTAPI_TOOL_SEARCH",
    "TOOL_SEARCH_MAX_RESULTS",
    "TOOL_SEARCH_THRESHOLD",
    "SERVER_NAME",
    "SERVER_HOST",
    "SERVER_PORT",
    "SERVER_TRANSPORT",
    "API_SPEC_URL",
    "API_BASE_URL",
)


@pytest.fixture(autouse=True)
def _clean_env():
    """Run every test with none of our environment variables set."""
    with patch.dict(os.environ, {}, clear=False) as _:
        for key in ENV_KEYS:
            os.environ.pop(key, None)
        yield


class TestConfig:
    """The Config dataclass itself."""

    def test_is_a_plain_dataclass(self):
        """Config no longer inherits from an external base class."""
        assert is_dataclass(Config)
        assert Config.__mro__[1:] == (object,)

    def test_defaults(self):
        config = Config()
        assert config.smartapi_id == ""
        assert config.smartapi_ids is None
        assert config.smartapi_exclude_ids is None
        assert config.smartapi_q == ""
        assert config.smartapi_api_set == ""
        assert config.server_name == "smartapi_mcp"
        assert config.host == "127.0.0.1"
        assert config.port == 8000
        assert config.transport == "stdio"
        assert config.facade == "auto"
        assert config.facade_threshold == 10
        assert config.facade_strict is False
        assert config.tool_search == "auto"
        assert config.tool_search_max_results == 10
        assert config.tool_search_threshold == 50

    def test_carries_only_the_fields_that_are_read(self):
        """Guard against the 40-field awslabs base class creeping back.

        The old base contributed ~35 unused fields (five auth schemes, Cognito,
        tag filtering, multi-spec composition). Anything added here should be
        something the package actually reads.
        """
        assert {f.name for f in fields(Config)} == {
            "api_base_url",
            "api_spec_url",
            "host",
            "port",
            "transport",
            "server_name",
            "smartapi_id",
            "smartapi_ids",
            "smartapi_exclude_ids",
            "smartapi_q",
            "smartapi_api_set",
            "facade",
            "facade_threshold",
            "facade_strict",
            "tool_search",
            "tool_search_max_results",
            "tool_search_threshold",
        }

    def test_fields_are_assignable(self):
        config = Config()
        config.smartapi_id = "test_id"
        config.smartapi_ids = ["id1", "id2"]
        config.smartapi_api_set = "biothings_core"
        assert config.smartapi_id == "test_id"
        assert config.smartapi_ids == ["id1", "id2"]
        assert config.smartapi_api_set == "biothings_core"


class TestLoadConfigDefaults:
    """load_config with nothing supplied."""

    def test_returns_defaults(self):
        config = load_config()
        assert isinstance(config, Config)
        assert config == Config()

    def test_none_args_is_accepted(self):
        assert load_config(None) == Config()


class TestLoadConfigEnvironment:
    """Environment-variable parsing."""

    def test_string_values(self):
        env = {
            "SMARTAPI_ID": "env_test_id",
            "SMARTAPI_Q": "env test query",
            "SMARTAPI_API_SET": "biothings_core",
            "SERVER_NAME": "env_server",
            "SERVER_HOST": "0.0.0.0",  # noqa: S104 - test value, not a bind
            "SERVER_TRANSPORT": "http",
        }
        with patch.dict(os.environ, env):
            config = load_config()
        assert config.smartapi_id == "env_test_id"
        assert config.smartapi_q == "env test query"
        assert config.smartapi_api_set == "biothings_core"
        assert config.server_name == "env_server"
        assert config.host == "0.0.0.0"  # noqa: S104
        assert config.transport == "http"

    def test_comma_separated_id_lists(self):
        env = {"SMARTAPI_IDS": "id1,id2", "SMARTAPI_EXCLUDE_IDS": "ex1,ex2"}
        with patch.dict(os.environ, env):
            config = load_config()
        assert config.smartapi_ids == ["id1", "id2"]
        assert config.smartapi_exclude_ids == ["ex1", "ex2"]

    def test_partial_environment_leaves_the_rest_at_defaults(self):
        env = {"SMARTAPI_ID": "partial_env_id", "SMARTAPI_Q": "partial env query"}
        with patch.dict(os.environ, env):
            config = load_config()
        assert config.smartapi_id == "partial_env_id"
        assert config.smartapi_q == "partial env query"
        assert config.smartapi_ids is None
        assert config.smartapi_api_set == ""
        assert config.server_name == "smartapi_mcp"

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("AUTO", "auto"),
            ("  Off  ", "off"),
            ("BM25", "bm25"),
        ],
    )
    def test_mode_values_are_normalised(self, value, expected):
        """Modes are lower-cased and stripped, so 'OFF' works like 'off'."""
        with patch.dict(os.environ, {"SMARTAPI_TOOL_SEARCH": value}):
            assert load_config().tool_search == expected
        with patch.dict(os.environ, {"SMARTAPI_FACADE": value}):
            assert load_config().facade == expected

    @pytest.mark.parametrize(
        ("value", "expected"),
        [
            ("1", True),
            ("true", True),
            ("YES", True),
            ("on", True),
            ("0", False),
            ("no", False),
        ],
    )
    def test_facade_strict_is_parsed_as_a_bool(self, value, expected):
        with patch.dict(os.environ, {"FACADE_STRICT": value}):
            assert load_config().facade_strict is expected

    def test_integer_values(self):
        env = {
            "FACADE_THRESHOLD": "3",
            "TOOL_SEARCH_MAX_RESULTS": "12",
            "TOOL_SEARCH_THRESHOLD": "99",
            "SERVER_PORT": "9001",
        }
        with patch.dict(os.environ, env):
            config = load_config()
        assert config.facade_threshold == 3
        assert config.tool_search_max_results == 12
        assert config.tool_search_threshold == 99
        assert config.port == 9001

    @pytest.mark.parametrize(
        "key",
        [
            "FACADE_THRESHOLD",
            "TOOL_SEARCH_MAX_RESULTS",
            "TOOL_SEARCH_THRESHOLD",
            "SERVER_PORT",
        ],
    )
    def test_unparseable_integers_fall_back_to_the_default(self, key):
        """A typo in a numeric env var must not crash the server at startup."""
        with patch.dict(os.environ, {key: "not-a-number"}):
            config = load_config()
        assert config == Config()

    @patch("smartapi_mcp.config.logger")
    def test_loaded_variables_are_logged(self, mock_logger):
        env = {"SMARTAPI_ID": "x", "SMARTAPI_Q": "y"}
        with patch.dict(os.environ, env):
            load_config()
        debug_calls = [
            call.args[0]
            for call in mock_logger.debug.call_args_list
            if call.args and str(call.args[0]).startswith("Loaded")
        ]
        assert len(debug_calls) == 1
        assert "Loaded 2 environment variables" in debug_calls[0]
        assert "SMARTAPI_ID" in debug_calls[0]
        assert "SMARTAPI_Q" in debug_calls[0]

    @patch("smartapi_mcp.config.logger")
    def test_nothing_logged_when_no_variables_are_set(self, mock_logger):
        load_config()
        debug_calls = [
            call
            for call in mock_logger.debug.call_args_list
            if call.args and str(call.args[0]).startswith("Loaded")
        ]
        assert debug_calls == []


class TestLoadConfigArgs:
    """CLI arguments, and their precedence over the environment."""

    def test_each_argument_reaches_config(self):
        args = SimpleNamespace(
            smartapi_id="args_id",
            smartapi_ids=["args_id1", "args_id2"],
            smartapi_exclude_ids=["ex1", "ex2"],
            smartapi_q="args query",
            api_set="biothings_all",
            server_name="custom_server",
            transport="http",
            host="10.0.0.1",
            port=9999,
            facade="on",
            facade_threshold=4,
            facade_strict=True,
            tool_search="regex",
            tool_search_max_results=7,
            tool_search_threshold=25,
        )
        config = load_config(args)
        assert config.smartapi_id == "args_id"
        assert config.smartapi_ids == ["args_id1", "args_id2"]
        assert config.smartapi_exclude_ids == ["ex1", "ex2"]
        assert config.smartapi_q == "args query"
        assert config.smartapi_api_set == "biothings_all"
        assert config.server_name == "custom_server"
        assert config.transport == "http"
        assert config.host == "10.0.0.1"
        assert config.port == 9999
        assert config.facade == "on"
        assert config.facade_threshold == 4
        assert config.facade_strict is True
        assert config.tool_search == "regex"
        assert config.tool_search_max_results == 7
        assert config.tool_search_threshold == 25

    def test_comma_separated_id_arguments_are_split(self):
        """argparse hands these over as raw strings, unlike programmatic callers."""
        args = SimpleNamespace(smartapi_ids="id1,id2", smartapi_exclude_ids="ex1,ex2")
        config = load_config(args)
        assert config.smartapi_ids == ["id1", "id2"]
        assert config.smartapi_exclude_ids == ["ex1", "ex2"]

    def test_args_override_environment(self):
        env = {
            "SMARTAPI_ID": "env_id",
            "SMARTAPI_Q": "env query",
            "SERVER_NAME": "env_server",
            "SERVER_PORT": "8000",
        }
        args = SimpleNamespace(
            smartapi_id="args_id",
            smartapi_q="args query",
            server_name="args_server",
            port=9999,
        )
        with patch.dict(os.environ, env):
            config = load_config(args)
        assert config.smartapi_id == "args_id"
        assert config.smartapi_q == "args query"
        assert config.server_name == "args_server"
        assert config.port == 9999

    def test_unset_args_do_not_shadow_environment(self):
        """argparse passes None for unset flags; None must not overwrite the env.

        ``load_config`` assigns from ``args`` whenever the attribute is truthy,
        so a non-None argparse default silently beat the environment on every
        run. ``tests/test_tool_search.py`` guards the parser side of this.
        """
        env = {
            "SMARTAPI_TOOL_SEARCH": "bm25",
            "SMARTAPI_FACADE": "off",
            "SERVER_PORT": "9001",
            "SERVER_HOST": "1.2.3.4",
        }
        args = SimpleNamespace(
            tool_search=None, facade=None, port=None, host=None, facade_strict=False
        )
        with patch.dict(os.environ, env):
            config = load_config(args)
        assert config.tool_search == "bm25"
        assert config.facade == "off"
        assert config.port == 9001
        assert config.host == "1.2.3.4"

    def test_empty_and_none_arguments_are_ignored(self):
        args = SimpleNamespace(smartapi_id="", smartapi_q=None, api_set="")
        config = load_config(args)
        assert config.smartapi_id == ""
        assert config.smartapi_q == ""
        assert config.smartapi_api_set == ""

    def test_missing_attributes_are_tolerated(self):
        """A caller may pass a namespace carrying only some of the fields."""
        args = SimpleNamespace(smartapi_id="test_id")
        config = load_config(args)
        assert config.smartapi_id == "test_id"
        assert config.smartapi_q == ""
        assert config.smartapi_api_set == ""

    @patch("smartapi_mcp.config.logger")
    def test_completion_is_logged_once(self, mock_logger):
        load_config()
        mock_logger.info.assert_called_once_with("SmartAPI Configuration loaded")
