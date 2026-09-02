"""
SmartAPI MCP Server Package

Create MCP servers for one or multiple APIs registered in SmartAPI registry.
"""

__version__ = "0.3.2"
__author__ = "BioThings Team"
__email__ = "help@biothings.io"

# Optional imports for when dependencies are available
try:
    from .biothings import build_biothings_facade, build_registry
    from .openapi import (
        SpecError,
        build_openapi_server,
        fetch_spec,
        resolve_internal_refs,
    )
    from .server import (
        build_server_for_set,
        get_mcp_server,
        get_merged_mcp_server,
        merge_mcp_servers,
    )
    from .smartapi import (
        PREDEFINED_API_SETS,
        get_base_server_url,
        get_predefined_api_set,
        get_smartapi_ids,
        get_smartapi_registry,
        load_api_spec,
    )

    __all__ = [
        "PREDEFINED_API_SETS",
        "SpecError",
        "build_biothings_facade",
        "build_openapi_server",
        "build_registry",
        "build_server_for_set",
        "fetch_spec",
        "get_base_server_url",
        "get_mcp_server",
        "get_merged_mcp_server",
        "get_predefined_api_set",
        "get_smartapi_ids",
        "get_smartapi_registry",
        "load_api_spec",
        "merge_mcp_servers",
        "resolve_internal_refs",
    ]
except ImportError:
    # Dependencies not available, only export version info
    __all__ = []
