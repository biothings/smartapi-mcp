"""
SmartAPI MCP Server Package

Create MCP servers for one or multiple APIs registered in SmartAPI registry.
"""

__version__ = "0.1.1"
__author__ = "BioThings Team"
__email__ = "help@biothings.io"

# Optional imports for when dependencies are available
try:
    from .server import get_mcp_server, get_merged_mcp_server, merge_mcp_servers
    from .smartapi import (
        PREDEFINED_API_SETS,
        get_base_server_url,
        get_predefined_api_set,
        get_smartapi_ids,
        load_api_spec,
    )

    __all__ = [
        "PREDEFINED_API_SETS",
        "get_base_server_url",
        "get_mcp_server",
        "get_merged_mcp_server",
        "get_predefined_api_set",
        "get_smartapi_ids",
        "load_api_spec",
        "merge_mcp_servers",
    ]
except ImportError:
    # Dependencies not available, only export version info
    __all__ = []
