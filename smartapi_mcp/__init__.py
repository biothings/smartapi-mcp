"""
SmartAPI MCP Server Package

Create MCP servers for one or multiple APIs registered in SmartAPI registry.
"""

__version__ = "0.1.0"
__author__ = "BioThings Team"
__email__ = "help@biothings.io"

# Optional imports for when dependencies are available
try:
    from .server import get_merged_mcp_server
    from .smartapi import get_base_server_url, get_smartapi_ids

    __all__ = ["get_base_server_url", "get_merged_mcp_server", "get_smartapi_ids"]
except ImportError:
    # Dependencies not available, only export version info
    __all__ = []
