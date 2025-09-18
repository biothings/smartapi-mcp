# SmartAPI MCP Server

Create MCP (Model Context Protocol) servers for one or multiple APIs registered in the SmartAPI registry.

[![Test](https://github.com/biothings/smartapi-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/biothings/smartapi-mcp/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/smartapi-mcp.svg)](https://badge.fury.io/py/smartapi-mcp)
[![Python versions](https://img.shields.io/pypi/pyversions/smartapi-mcp.svg)](https://pypi.org/project/smartapi-mcp/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

The SmartAPI MCP Server enables integration between MCP-compatible clients and APIs registered in the SmartAPI registry. This allows for seamless discovery and interaction with bioinformatics and life sciences APIs through standardized MCP protocols.

Built on top of the [AWS Labs OpenAPI MCP Server](https://github.com/awslabs/openapi-mcp-server), this project extends MCP support to the extensive collection of APIs available in the SmartAPI registry, with special focus on bioinformatics and life sciences APIs.

## Requirements

- Python 3.10 or higher
- Network access to SmartAPI registry (https://smart-api.info)
- Dependencies: `awslabs_openapi_mcp_server>=0.2.4`

## Features

- 🔍 **SmartAPI Integration**: Direct integration with the SmartAPI registry for API discovery
- 🏗️ **MCP Protocol Support**: Full MCP (Model Context Protocol) server implementation
- 🔄 **Async Architecture**: Built with modern Python async/await patterns for high performance
- 📖 **OpenAPI Validation**: Automatic OpenAPI specification parsing and validation
- 🛠️ **CLI Interface**: Easy-to-use command-line interface with multiple configuration options
- 🧬 **Bioinformatics Focus**: Pre-configured API sets for bioinformatics and life sciences
- 🎯 **Flexible Configuration**: Support for environment variables, arguments, and configuration files
- 🚀 **Multiple Transport Modes**: Support for both stdio and HTTP transport protocols
- 🧪 **Comprehensive Testing**: Full test suite with 99% code coverage

## Installation

### From PyPI (recommended)

```bash
pip install smartapi-mcp
```

### From Source

```bash
git clone https://github.com/biothings/smartapi-mcp.git
cd smartapi-mcp
pip install -e .
```

### Development Installation

```bash
git clone https://github.com/biothings/smartapi-mcp.git
cd smartapi-mcp
pip install -e ".[dev]"
```

## Using with MCP Clients

### Using with uvx (Recommended)

[uvx](https://github.com/astral-sh/uv) is a tool for running Python applications in isolated environments. This is the recommended way to run smartapi-mcp for MCP client integration:

#### Installation and Basic Usage

```bash
# Install uvx if you haven't already
curl -LsSf https://astral.sh/uv/install.sh | sh
# or with homebrew on macOS
brew install uv

# Run smartapi-mcp with uvx (automatically installs if needed)
uvx smartapi-mcp --api_set biothings_core

# Run with specific version
uvx smartapi-mcp@0.1.0 --api_set biothings_core

# Run with additional arguments
uvx smartapi-mcp --smartapi_id 59dce17363dce279d389100834e43648 --server_name "MyGene MCP Server"
```

#### Using with Claude Desktop

To use smartapi-mcp with Claude Desktop, add the following configuration to your Claude Desktop configuration file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`

**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "smartapi-biothings-core": {
      "command": "uvx",
      "args": ["smartapi-mcp", "--api_set", "biothings_core", "--server_name", "BioThings Core APIs"]
    },
    "smartapi-mygene": {
      "command": "uvx",
      "args": ["smartapi-mcp", "--smartapi_id", "59dce17363dce279d389100834e43648", "--server_name", "MyGene.info API"]
    },
    "smartapi-myvariant": {
      "command": "uvx",
      "args": ["smartapi-mcp", "--smartapi_id", "09c8782d9f4027712e65b95424adba79", "--server_name", "MyVariant.info API"]
    }
  }
}
```

#### Using with Other MCP Clients

For other MCP clients that support external MCP servers, you can typically configure them by providing:

- **Command**: `uvx`
- **Arguments**: `["smartapi-mcp", "--api_set", "biothings_core"]` (or other desired arguments)
- **Working Directory**: Optional, can be any directory
- **Environment Variables**: Optional, see [Environment Variables](#environment-variables) section

### MCP Server Configuration Examples

#### Basic Bioinformatics Setup

```json
{
  "mcpServers": {
    "biothings-core": {
      "command": "uvx",
      "args": ["smartapi-mcp", "--api_set", "biothings_core"],
      "env": {
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

#### Advanced Multi-API Setup

```json
{
  "mcpServers": {
    "biothings-comprehensive": {
      "command": "uvx",
      "args": [
        "smartapi-mcp",
        "--smartapi_ids",
        "59dce17363dce279d389100834e43648,09c8782d9f4027712e65b95424adba79,8f08d1446e0bb9c2b323713ce83e2bd3",
        "--server_name",
        "Comprehensive Bioinformatics APIs",
        "--log-level",
        "DEBUG"
      ]
    }
  }
}
```

#### Development/Testing Setup

```json
{
  "mcpServers": {
    "smartapi-dev": {
      "command": "uvx",
      "args": [
        "smartapi-mcp",
        "--api_set",
        "biothings_test",
        "--log-level",
        "DEBUG"
      ],
      "env": {
        "SMARTAPI_LOG_LEVEL": "DEBUG"
      }
    }
  }
}
```

### Environment Variables for MCP Configuration

You can also use environment variables in your MCP client configuration:

```json
{
  "mcpServers": {
    "smartapi-configured": {
      "command": "uvx",
      "args": ["smartapi-mcp"],
      "env": {
        "SMARTAPI_API_SET": "biothings_core",
        "SERVER_NAME": "BioThings Core MCP Server",
        "LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Alternative Installation Methods for MCP Clients

#### Using pip in a Virtual Environment

If you prefer not to use uvx, you can create a dedicated virtual environment:

```bash
# Create and activate virtual environment
python -m venv smartapi-mcp-env
source smartapi-mcp-env/bin/activate  # On Windows: smartapi-mcp-env\Scripts\activate

# Install smartapi-mcp
pip install smartapi-mcp

# Test the installation
smartapi-mcp --api_set biothings_core
```

Then configure your MCP client to use the full path to the executable:

```json
{
  "mcpServers": {
    "smartapi-biothings": {
      "command": "/path/to/smartapi-mcp-env/bin/smartapi-mcp",
      "args": ["--api_set", "biothings_core"]
    }
  }
}
```

#### Using System-wide Installation

```bash
# Install globally (not recommended for most users)
pip install smartapi-mcp

# Find the installation path
which smartapi-mcp
```

MCP client configuration:

```json
{
  "mcpServers": {
    "smartapi-biothings": {
      "command": "smartapi-mcp",
      "args": ["--api_set", "biothings_core"]
    }
  }
}
```

### Troubleshooting MCP Client Integration

#### Server Not Starting

1. **Check uvx installation**:
   ```bash
   uvx --version
   ```

2. **Test server manually**:
   ```bash
   uvx smartapi-mcp --api_set biothings_core --log-level DEBUG
   ```

3. **Check MCP client logs** for specific error messages

#### Tools Not Appearing in Client

1. **Verify server is running** with tools registered:
   ```bash
   uvx smartapi-mcp --api_set biothings_core --log-level DEBUG 2>&1 | grep -i "tool"
   ```

2. **Check API connectivity**:
   ```bash
   curl -s https://mygene.info/v3/metadata | head -20
   ```

3. **Try a smaller API set** first:
   ```bash
   uvx smartapi-mcp --smartapi_id 59dce17363dce279d389100834e43648
   ```

#### Performance Issues

- Use specific SmartAPI IDs instead of large API sets
- Enable only the APIs you actually need
- Consider using HTTP transport for better performance with multiple concurrent requests:
  ```json
  {
    "mcpServers": {
      "smartapi-http": {
        "command": "uvx",
        "args": ["smartapi-mcp", "--api_set", "biothings_core", "--transport", "http", "--port", "8001"]
      }
    }
  }
  ```

## Quick Start

### Command Line Usage

#### Start with a predefined API set (recommended)

```bash
# Use BioThings core APIs (MyGene, MyVariant, MyChem, MyDisease)
smartapi-mcp --api_set biothings_core

# Use all BioThings APIs (with some exclusions)
smartapi-mcp --api_set biothings_all
```

#### Start with specific SmartAPI IDs

```bash
# Single API
smartapi-mcp --smartapi_id 59dce17363dce279d389100834e43648

# Multiple APIs
smartapi-mcp --smartapi_ids "59dce17363dce279d389100834e43648,09c8782d9f4027712e65b95424adba79"
```

#### Start with HTTP transport (instead of stdio)

```bash
# HTTP mode on localhost:8000 (default)
smartapi-mcp --api_set biothings_core --transport http

# Custom host and port
smartapi-mcp --api_set biothings_core --transport http --host 0.0.0.0 --port 9000
```

#### Advanced options

```bash
# Custom logging level
smartapi-mcp --api_set biothings_core --log-level DEBUG

# Custom server name
smartapi-mcp --api_set biothings_core --server_name "My Custom MCP Server"

# Query-based API discovery
smartapi-mcp --smartapi_q "tags.name=biothings"

# Exclude specific APIs
smartapi-mcp --api_set biothings_all --smartapi_exclude_ids "api_id_1,api_id_2"
```

### Python API Usage

```python
import asyncio
from smartapi_mcp import (
    get_smartapi_ids,
    load_api_spec,
    get_mcp_server,
    get_merged_mcp_server,
    PREDEFINED_API_SETS
)

async def main():
    # Get SmartAPI IDs using a query
    smartapi_ids = await get_smartapi_ids("tags.name=biothings")
    print(f"Found {len(smartapi_ids)} APIs matching the query")
    
    # Load API specification for a specific SmartAPI
    api_spec = load_api_spec("59dce17363dce279d389100834e43648")  # MyGene.info
    print(f"Loaded API: {api_spec.get('info', {}).get('title', 'Unknown')}")
    
    # Create MCP server for a single API
    server = await get_mcp_server(
        smartapi_id="59dce17363dce279d389100834e43648",
        server_name="MyGene MCP Server"
    )
    
    # Create merged MCP server for multiple APIs (recommended approach)
    merged_server = await get_merged_mcp_server(
        api_set="biothings_core",  # Use predefined set
        server_name="BioThings Core MCP Server"
    )
    
    # Or with specific SmartAPI IDs
    merged_server = await get_merged_mcp_server(
        smartapi_ids=[
            "59dce17363dce279d389100834e43648",  # MyGene.info
            "09c8782d9f4027712e65b95424adba79",  # MyVariant.info
        ],
        server_name="Custom MCP Server"
    )
    
    # Show available predefined API sets
    print(f"Available API sets: {PREDEFINED_API_SETS}")
    
    # Run server with stdio transport (default for MCP)
    merged_server.run()
    
    # Or run with HTTP transport
    # merged_server.run(transport="http", host="localhost", port=8000)

if __name__ == "__main__":
    asyncio.run(main())
```

## API Examples

### BioThings Core APIs

When you use `--api_set biothings_core`, you get access to these powerful bioinformatics APIs:

1. **MyGene.info** (`59dce17363dce279d389100834e43648`): Gene annotation and information
2. **MyVariant.info** (`09c8782d9f4027712e65b95424adba79`): Variant annotation and information  
3. **MyChem.info** (`8f08d1446e0bb9c2b323713ce83e2bd3`): Chemical and drug information
4. **MyDisease.info** (`671b45c0301c8624abbd26ae78449ca2`): Disease information and associations

### Usage with MCP Clients

Once the server is running, MCP-compatible clients can discover and use the available tools. Each API endpoint becomes an available MCP tool with:

- **Tool discovery**: Clients can list all available API endpoints
- **Parameter validation**: Automatic parameter validation based on OpenAPI specs
- **Rich descriptions**: Each tool includes detailed descriptions from the API documentation
- **Error handling**: Proper error responses for invalid requests

## Configuration

The server supports multiple configuration methods:

### Environment Variables

```bash
# SmartAPI configuration
export SMARTAPI_ID="59dce17363dce279d389100834e43648"
export SMARTAPI_IDS="id1,id2,id3"
export SMARTAPI_Q="tags.name=biothings"
export SMARTAPI_API_SET="biothings_core"
export SMARTAPI_EXCLUDE_IDS="exclude_id1,exclude_id2"

# Server configuration
export SERVER_NAME="My SmartAPI MCP Server"
export TRANSPORT="http"
export HOST="localhost"
export PORT="8000"

# Then run without arguments
smartapi-mcp
```

### Command Line Arguments

All configuration can be provided via command line arguments (see Quick Start section above).

### Predefined API Sets

The following predefined API sets are available:

- **`biothings_core`**: Core BioThings APIs (MyGene, MyVariant, MyChem, MyDisease)
- **`biothings_test`**: Core APIs plus SemmedDB (useful for testing)
- **`biothings_all`**: All BioThings APIs (with some exclusions for stability)

### Configuration Priority

1. Command line arguments (highest priority)
2. Environment variables
3. Default values (lowest priority)

## Development

### Setting up Development Environment

```bash
# Clone the repository
git clone https://github.com/biothings/smartapi-mcp.git
cd smartapi-mcp

# Install development dependencies
pip install -e ".[dev]"
```

### Running Tests

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=smartapi_mcp --cov-report=html

# Run specific test file
pytest tests/test_basic.py
```

### Code Quality

```bash
# Check and fix linting issues
ruff check .
ruff check . --fix

# Format code
ruff format .
```

### Building the Package

```bash
# Build source and wheel distributions
python -m build

# Check the built package
twine check dist/*
```

## Publishing to PyPI

### Manual Publishing

```bash
# Build the package
python -m build

# Upload to Test PyPI (optional)
twine upload --repository testpypi dist/*

# Upload to PyPI
twine upload dist/*
```

### Automated Publishing

This repository includes GitHub Actions workflows for automated testing and publishing:

- **Test Workflow** (`.github/workflows/test.yml`): Runs on every push and pull request
- **Publish Workflow** (`.github/workflows/publish.yml`): Publishes to PyPI on release

To publish a new version:

1. Update the version in `pyproject.toml` and `smartapi_mcp/__init__.py`
2. Commit the version changes
3. Create and push a git tag: `git tag v0.1.0 && git push origin v0.1.0`
4. Create a new release on GitHub
5. The publish workflow will automatically build and upload to PyPI

### Manual Workflow Trigger

You can also manually trigger the publish workflow to upload to Test PyPI:

1. Go to the Actions tab in your GitHub repository
2. Select "Publish Python Package"
3. Click "Run workflow"
4. Choose "Publish to Test PyPI" option

## Contributing

We welcome contributions! Please see our contributing guidelines for details.

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Add tests for your changes
5. Ensure tests pass (`pytest`)
6. Commit your changes (`git commit -m 'Add amazing feature'`)
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Troubleshooting

### Common Issues

#### No tools or resources registered

```
WARNING: No tools or resources were registered. This might indicate an issue with the API specification or authentication.
```

**Solution**: This usually happens when:
- The SmartAPI ID is invalid or the API is down
- The OpenAPI specification has validation errors
- Network connectivity issues

Try with a known working API set: `smartapi-mcp --api_set biothings_core`

#### Server fails to start

**Check your Python version**: Requires Python 3.10+
```bash
python --version
```

**Verify installation**:
```bash
pip show smartapi-mcp
```

#### HTTP mode connection issues

If using HTTP transport mode and clients can't connect:
- Check if the port is available: `netstat -an | grep :8000`
- Try binding to all interfaces: `--host 0.0.0.0`
- Check firewall settings

### Getting Help

1. Enable debug logging: `--log-level DEBUG`
2. Check the [GitHub Issues](https://github.com/biothings/smartapi-mcp/issues)
3. Contact us at help@biothings.io

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Related Projects

- **[SmartAPI Registry](https://smart-api.info/)** - Registry of biomedical and life sciences APIs
- **[Model Context Protocol (MCP)](https://modelcontextprotocol.io/)** - Standard protocol for AI model-tool integration
- **[BioThings APIs](https://biothings.io/)** - High-performance bioinformatics APIs
- **[AWS Labs OpenAPI MCP Server](https://github.com/awslabs/openapi-mcp-server)** - Base MCP server framework

## Citation

If you use SmartAPI MCP Server in your research or applications, please cite:

```
SmartAPI MCP Server: Bridging Bioinformatics APIs with Model Context Protocol
BioThings Team. (2024). https://github.com/biothings/smartapi-mcp
```

## Support

For questions and support:

- 📖 **Documentation**: [README](https://github.com/biothings/smartapi-mcp#readme)
- 🐛 **Bug Reports**: [GitHub Issues](https://github.com/biothings/smartapi-mcp/issues)
- 💬 **Questions**: [GitHub Discussions](https://github.com/biothings/smartapi-mcp/discussions)
- 📧 **Email**: help@biothings.io

---

**SmartAPI MCP Server** is developed and maintained by the [BioThings Team](https://biothings.io) at The Scripps Research Institute.
