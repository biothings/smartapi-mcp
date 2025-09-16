"""
SmartAPI MCP Server Package

Create MCP servers for one or multiple APIs registered in SmartAPI registry.
"""

__version__ = "0.1.0"
__author__ = "BioThings Team"
__email__ = "help@biothings.io"

# Optional imports for when dependencies are available
try:
    from .server import SmartAPIMCPServer
    from .smartapi import SmartAPIRegistry
    __all__ = ["SmartAPIMCPServer", "SmartAPIRegistry"]
except ImportError:
    # Dependencies not available, only export version info
    __all__ = []