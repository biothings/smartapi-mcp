"""
Test suite for CLI module

This test suite provides comprehensive coverage for the smartapi_mcp CLI module,
testing all aspects of command-line interface functionality including:

- Argument parsing for different API sets, modes, and ports
- Server initialization with biothings_core and biothings API sets
- HTTP and stdio transport modes
- Error handling and edge cases
- Signal handler setup and logging
- Tool/resource counting and validation

The tests use extensive mocking to isolate CLI functionality from external
dependencies like actual API calls and server startup.

Test Coverage Areas:
- TestCLI: Main functionality tests
- TestCLIEdgeCases: Error conditions and edge cases

Key Mock Dependencies:
- get_merged_mcp_server: Mocked server creation
- get_all_counts: Mocked resource counting
- setup_signal_handlers: Mocked signal setup
- logger: Mocked logging calls
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from smartapi_mcp.cli import main


class TestCLI:
    """Test cases for CLI functionality."""

    def test_argument_parser_default_values(self):
        """Test that argument parser sets correct default values."""
        with patch("sys.argv", ["smartapi-mcp"]):
            parser = argparse.ArgumentParser(
                description=(
                    "Create MCP tools based on multiple registered SmartAPI APIs."
                )
            )
            parser.add_argument("--api_set", help="the set of predefined SmartAPI APIs")
            parser.add_argument("--mode", help="The mode of MCP server")
            parser.add_argument("--port", type=int, default=8001, help="HTTP port")

            args = parser.parse_args([])
            assert args.api_set is None
            assert args.mode is None
            assert args.port == 8001

    def test_argument_parser_with_values(self):
        """Test argument parser with provided values."""
        parser = argparse.ArgumentParser()
        parser.add_argument("--api_set")
        parser.add_argument("--mode")
        parser.add_argument("--port", type=int, default=8001)

        args = parser.parse_args(
            ["--api_set", "biothings_core", "--mode", "http", "--port", "9000"]
        )

        assert args.api_set == "biothings_core"
        assert args.mode == "http"
        assert args.port == 9000

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("smartapi_mcp.cli.setup_signal_handlers")
    @patch("smartapi_mcp.cli.logger")
    @patch("sys.argv", ["smartapi-mcp", "--api_set", "biothings_core"])
    def test_main_biothings_core_stdio_mode(
        self, mock_logger, mock_setup_signals, mock_get_counts, mock_get_server
    ):
        """Test main function with biothings_core API set and stdio mode."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (
            1,
            5,
            3,
            2,
        )  # prompt, tool, resource, resource_template counts

        # Run main
        main()

        # Verify biothings_core smartapi_ids were used
        expected_ids = [
            "59dce17363dce279d389100834e43648",  # MyGene.info
            "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
            "8f08d1446e0bb9c2b323713ce83e2bd3",  # MyChem.info
            "671b45c0301c8624abbd26ae78449ca2",  # MyDisease.info
            "1d288b3a3caf75d541ffaae3aab386c8",  # SemmedDB
        ]
        mock_get_server.assert_called_once()
        call_kwargs = mock_get_server.call_args[1]
        assert call_kwargs["smartapi_ids"] == expected_ids
        assert call_kwargs["server_name"] == "smartapi_mcp"

        # Verify signal handlers were set up
        mock_setup_signals.assert_called_once()

        # Verify counts were retrieved and logged
        mock_get_counts.assert_called_once_with(mock_server)
        mock_logger.info.assert_any_call(
            "Server components: 1 prompts, 5 tools, 3 resources, 2 resource templates"
        )

        # Verify server runs with default stdio mode
        mock_server.run.assert_called_once_with()

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("sys.argv", ["smartapi-mcp", "--api_set", "biothings"])
    def test_main_biothings_api_set(self, mock_get_counts, mock_get_server):
        """Test main function with biothings API set (default behavior)."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (2, 10, 5, 3)

        # Run main
        main()

        # Verify biothings query and exclusions were used
        mock_get_server.assert_called_once()
        call_kwargs = mock_get_server.call_args[1]

        expected_query = (
            "_status.uptime_status:pass AND tags.name=biothings AND NOT tags.name=trapi"
        )
        expected_excluded = [
            "1c9be9e56f93f54192dcac203f21c357",  # BioThings mabs API
            "5a4c41bf2076b469a0e9cfcf2f2b8f29",  # Translator Annotation Service
            "cc857d5b7c8b7609b5bbb38ff990bfff",  # BioThings GO Biological Process API
            "f339b28426e7bf72028f60feefcd7465",  # BioThings GO Cellular Component API
            "34bad236d77bea0a0ee6c6cba5be54a6",  # BioThings GO Molecular Function API
        ]

        assert call_kwargs["smartapi_q"] == expected_query
        assert call_kwargs["server_name"] == "smartapi_mcp"
        assert call_kwargs["exclude_ids"] == expected_excluded

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("smartapi_mcp.cli.logger")
    @patch("sys.argv", ["smartapi-mcp", "--mode", "http", "--port", "9001"])
    def test_main_http_mode(self, mock_logger, mock_get_counts, mock_get_server):
        """Test main function with HTTP mode."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (1, 3, 2, 1)

        # Run main
        main()

        # Verify HTTP mode logging and server run
        mock_logger.info.assert_any_call("Running server with HTTP transport")
        mock_server.run.assert_called_once_with(
            transport="http", host="127.0.0.1", port=9001
        )

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("smartapi_mcp.cli.logger")
    @patch("sys.argv", ["smartapi-mcp"])
    def test_main_stdio_mode_default(
        self, mock_logger, mock_get_counts, mock_get_server
    ):
        """Test main function with default stdio mode."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (1, 3, 2, 1)

        # Run main
        main()

        # Verify stdio mode logging and server run
        mock_logger.info.assert_any_call("Running server with stdio transport")
        mock_server.run.assert_called_once_with()

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("smartapi_mcp.cli.logger")
    @patch("sys.argv", ["smartapi-mcp"])
    def test_main_no_tools_or_resources_warning(
        self, mock_logger, mock_get_counts, mock_get_server
    ):
        """Test main function warns when no tools or resources are available."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (1, 0, 0, 1)  # No tools or resources

        # Run main
        main()

        # Verify warning is logged
        mock_logger.warning.assert_called_once_with(
            "No tools or resources were registered. This might "
            "indicate an issue "
            "with the API specification or authentication."
        )

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("smartapi_mcp.cli.logger")
    @patch("sys.argv", ["smartapi-mcp"])
    def test_main_counts_exception_handling(
        self, mock_logger, mock_get_counts, mock_get_server
    ):
        """Test main function handles exceptions during count retrieval."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.side_effect = Exception("Count error")

        # Run main and expect sys.exit(1)
        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

        # Verify error logging
        mock_logger.error.assert_any_call(
            "Error counting tools and resources: Count error"
        )
        mock_logger.error.assert_any_call(
            "Server shutting down due to error in tool/resource registration."
        )

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("sys.argv", ["smartapi-mcp", "--api_set", "unknown"])
    def test_main_unknown_api_set_defaults_to_biothings(
        self, mock_get_counts, mock_get_server
    ):
        """Test main function defaults to biothings behavior for unknown API set."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (1, 3, 2, 1)

        # Run main
        main()

        # Verify it uses biothings query (default behavior)
        mock_get_server.assert_called_once()
        call_kwargs = mock_get_server.call_args[1]

        expected_query = (
            "_status.uptime_status:pass AND tags.name=biothings AND NOT tags.name=trapi"
        )
        assert call_kwargs["smartapi_q"] == expected_query

    @patch("smartapi_mcp.cli.argparse.ArgumentParser.parse_args")
    def test_argument_parsing_integration(self, mock_parse_args):
        """Test that argument parsing works correctly with all options."""
        # Mock different argument combinations
        mock_args = MagicMock()
        mock_args.api_set = "biothings_core"
        mock_args.mode = "http"
        mock_args.port = 8080
        mock_parse_args.return_value = mock_args

        with (
            patch("smartapi_mcp.cli.get_merged_mcp_server") as mock_get_server,
            patch("smartapi_mcp.cli.get_all_counts") as mock_get_counts,
            patch("smartapi_mcp.cli.setup_signal_handlers"),
        ):
            mock_server = MagicMock()
            mock_get_server.return_value = mock_server
            mock_get_counts.return_value = (1, 3, 2, 1)

            main()

            # Verify the parsed arguments were used
            assert mock_parse_args.called
            mock_server.run.assert_called_once_with(
                transport="http", host="127.0.0.1", port=8080
            )


class TestCLIEdgeCases:
    """Test edge cases and error conditions."""

    @patch("sys.argv", ["smartapi-mcp", "--port", "invalid"])
    def test_invalid_port_argument(self):
        """Test that invalid port argument is handled by argparse."""
        with pytest.raises(SystemExit):
            main()

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("sys.argv", ["smartapi-mcp", "--api_set", ""])
    def test_empty_api_set(self, mock_get_counts, mock_get_server):
        """Test main function with empty API set string."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (1, 3, 2, 1)

        # Run main - should default to biothings behavior
        main()

        # Verify it uses biothings query (default behavior)
        mock_get_server.assert_called_once()
        call_kwargs = mock_get_server.call_args[1]
        assert "smartapi_q" in call_kwargs

    @patch("smartapi_mcp.cli.get_merged_mcp_server")
    @patch("smartapi_mcp.cli.get_all_counts")
    @patch("smartapi_mcp.cli.logger")
    @patch("sys.argv", ["smartapi-mcp", "--mode", "invalid"])
    def test_invalid_mode_still_runs_stdio(
        self, mock_logger, mock_get_counts, mock_get_server
    ):
        """Test that invalid mode defaults to stdio."""
        # Setup mocks
        mock_server = MagicMock()
        mock_get_server.return_value = mock_server
        mock_get_counts.return_value = (1, 3, 2, 1)

        # Run main
        main()

        # Should default to stdio mode
        mock_logger.info.assert_any_call("Running server with stdio transport")
        mock_server.run.assert_called_once_with()
