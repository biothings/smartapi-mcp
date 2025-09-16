# SmartAPI MCP Server

Create MCP (Model Context Protocol) servers for one or multiple APIs registered in the SmartAPI registry.

[![Test](https://github.com/biothings/smartapi-mcp/actions/workflows/test.yml/badge.svg)](https://github.com/biothings/smartapi-mcp/actions/workflows/test.yml)
[![PyPI version](https://badge.fury.io/py/smartapi-mcp.svg)](https://badge.fury.io/py/smartapi-mcp)
[![Python versions](https://img.shields.io/pypi/pyversions/smartapi-mcp.svg)](https://pypi.org/project/smartapi-mcp/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

## Overview

The SmartAPI MCP Server enables integration between MCP-compatible clients and APIs registered in the SmartAPI registry. This allows for seamless discovery and interaction with bioinformatics and life sciences APIs through standardized MCP protocols.

## Features

- 🔍 **API Discovery**: Search and discover APIs from the SmartAPI registry
- 🏗️ **MCP Integration**: Full MCP (Model Context Protocol) server implementation
- 🔄 **Async Support**: Built with modern Python async/await patterns
- 📖 **OpenAPI Integration**: Automatic OpenAPI specification parsing and validation
- 🛠️ **CLI Interface**: Easy-to-use command-line interface
- 🧪 **Testing**: Comprehensive test suite with async testing support

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

## Quick Start

### Command Line Usage

Start the MCP server:

```bash
smartapi-mcp server --port 3000
```

With custom configuration:

```bash
smartapi-mcp server --port 3000 --config config.json --log-level DEBUG
```

### Python API Usage

```python
import asyncio
from smartapi_mcp import SmartAPIMCPServer, SmartAPIRegistry

async def main():
    # Initialize SmartAPI registry client
    async with SmartAPIRegistry() as registry:
        # Search for APIs
        apis = await registry.search_apis("gene", limit=5)
        print(f"Found {len(apis)} APIs")
        
        # Get specific API specification
        api_spec = await registry.get_api_spec("some-api-id")
        if api_spec:
            print(f"API: {api_spec.get('info', {}).get('title', 'Unknown')}")
    
    # Initialize and start MCP server
    server = SmartAPIMCPServer()
    await server.start()
    
    # Server info
    info = server.get_server_info()
    print(f"Server: {info['name']} v{info['version']}")

if __name__ == "__main__":
    asyncio.run(main())
```

## Configuration

The server can be configured using a JSON configuration file:

```json
{
    "smartapi": {
        "base_url": "https://smart-api.info/api",
        "default_limit": 10
    },
    "server": {
        "host": "localhost",
        "port": 3000
    },
    "logging": {
        "level": "INFO"
    }
}
```

## Development

### Setting up Development Environment

```bash
# Clone the repository
git clone https://github.com/biothings/smartapi-mcp.git
cd smartapi-mcp

# Install development dependencies
pip install -r requirements-dev.txt

# Install package in editable mode
pip install -e .
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
# Format code
black .

# Sort imports
isort .

# Lint code
flake8 .
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
2. Create a new release on GitHub
3. The publish workflow will automatically build and upload to PyPI

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

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Links

- [SmartAPI Registry](https://smart-api.info/)
- [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
- [BioThings](https://biothings.io/)

## Support

For questions and support, please:

- Open an issue on [GitHub Issues](https://github.com/biothings/smartapi-mcp/issues)
- Contact the BioThings team at help@biothings.io
