"""
Command Line Interface for SmartAPI MCP Server

Provides CLI commands for running and managing the SmartAPI MCP server.
"""

import argparse
import asyncio
import logging
import sys
from .server import SmartAPIMCPServer
from . import __version__


def setup_logging(level: str = "INFO"):
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, level.upper()),
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )


async def run_server(args):
    """Run the SmartAPI MCP server."""
    setup_logging(args.log_level)
    
    config = {}
    if args.config:
        # TODO: Load configuration from file
        pass
        
    server = SmartAPIMCPServer(config)
    
    try:
        await server.start()
        print(f"SmartAPI MCP Server running on port {args.port}")
        # Keep server running
        while True:
            await asyncio.sleep(1)
    except KeyboardInterrupt:
        print("\nShutting down server...")
    finally:
        await server.stop()


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="SmartAPI MCP Server - Create MCP servers for SmartAPI registry APIs"
    )
    parser.add_argument(
        "--version", 
        action="version", 
        version=f"smartapi-mcp {__version__}"
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Available commands")
    
    # Server command
    server_parser = subparsers.add_parser("server", help="Run the MCP server")
    server_parser.add_argument(
        "--port", 
        type=int, 
        default=3000, 
        help="Port to run the server on (default: 3000)"
    )
    server_parser.add_argument(
        "--config", 
        help="Path to configuration file"
    )
    server_parser.add_argument(
        "--log-level", 
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging level (default: INFO)"
    )
    
    args = parser.parse_args()
    
    if args.command == "server":
        asyncio.run(run_server(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()