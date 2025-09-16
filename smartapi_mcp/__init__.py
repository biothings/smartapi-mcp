"""
SmartAPI MCP Server Package

Create MCP servers for one or multiple APIs registered in SmartAPI registry.
"""

__version__ = "0.1.0"
__author__ = "BioThings Team"
__email__ = "help@biothings.io"

# Optional imports for when dependencies are available
try:
    from .server import get_mcp_server, get_merged_mcp_server, merge_mcp_servers
    from .smartapi import get_base_server_url, get_smartapi_ids, load_api_spec

    __all__ = [
        "get_base_server_url",
        "get_mcp_server",
        "get_merged_mcp_server",
        "get_smartapi_ids",
        "load_api_spec",
        "merge_mcp_server",
    ]
except ImportError:
    # Dependencies not available, only export version info
    __all__ = []
