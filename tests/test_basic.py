"""
Basic tests for smartapi-mcp package
"""

import pytest
import asyncio
from smartapi_mcp import SmartAPIMCPServer, SmartAPIRegistry


def test_package_imports():
    """Test that main package imports work correctly."""
    assert SmartAPIMCPServer is not None
    assert SmartAPIRegistry is not None


def test_server_initialization():
    """Test SmartAPI MCP Server initialization."""
    server = SmartAPIMCPServer()
    assert server is not None
    assert server.config == {}
    
    config = {"test": "value"}
    server_with_config = SmartAPIMCPServer(config)
    assert server_with_config.config == config


def test_server_info():
    """Test server info method."""
    server = SmartAPIMCPServer()
    info = server.get_server_info()
    
    assert "name" in info
    assert "version" in info
    assert "description" in info
    assert info["name"] == "smartapi-mcp"


def test_smartapi_registry_initialization():
    """Test SmartAPI Registry initialization."""
    registry = SmartAPIRegistry()
    assert registry.base_url == "https://smart-api.info/api"
    
    custom_url = "https://custom.api.url"
    custom_registry = SmartAPIRegistry(custom_url)
    assert custom_registry.base_url == custom_url


@pytest.mark.asyncio
async def test_server_lifecycle():
    """Test server start/stop lifecycle."""
    server = SmartAPIMCPServer()
    
    # Test initialization
    await server.initialize()
    
    # Test start and stop (should not raise exceptions)
    await server.start()
    await server.stop()


@pytest.mark.asyncio
async def test_smartapi_registry_context_manager():
    """Test SmartAPI Registry as async context manager."""
    async with SmartAPIRegistry() as registry:
        assert registry.session is not None
    
    # Session should be closed after context exit
    assert registry.session.closed