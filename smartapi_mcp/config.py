import os
from dataclasses import fields
from typing import Any

from awslabs.openapi_mcp_server import logger
from awslabs.openapi_mcp_server.api import config as _config


class Config(_config.Config):
    """Subclass of Config to add extra configuration options"""

    smartapi_id: str = ""
    smartapi_ids: list[str] | None = None
    smartapi_exclude_ids: list[str] | None = None
    smartapi_q: str = ""
    smartapi_api_set: str = ""
    server_name: str = "smartapi-mcp"


def load_config(args: Any = None) -> Config:
    config = Config()
    _cfg = _config.load_config(args)
    for field in fields(_cfg):
        setattr(config, field.name, getattr(_cfg, field.name))

    # define the following SmartAPI-specific environment variables
    env_vars = {
        "SMARTAPI_ID": (lambda v: setattr(config, "smartapi_id", v)),
        "SMARTAPI_IDS": (lambda v: setattr(config, "smartapi_ids", v.split(","))),
        "SMARTAPI_EXCLUDE_IDS": (
            lambda v: setattr(config, "smartapi_exclude_ids", v.split(","))
        ),
        "SMARTAPI_Q": (lambda v: setattr(config, "smartapi_q", v)),
        "SMARTAPI_API_SET": (lambda v: setattr(config, "smartapi_api_set", v)),
        "SERVER_NAME": (lambda v: setattr(config, "server_name", v)),
    }

    # Load environment variables
    env_loaded = {}
    for key, setter in env_vars.items():
        if key in os.environ:
            env_value = os.environ[key]
            setter(env_value)
            env_loaded[key] = env_value

    if env_loaded:
        logger.debug(
            f"Loaded {len(env_loaded)} SmartAPI-specific environment variables: "
            f"{', '.join(env_loaded.keys())}"
        )

    # Load from arguments
    if args:
        if hasattr(args, "smartapi_id") and args.smartapi_id:
            logger.debug(f"Setting SmartAPI id from arguments: {args.smartapi_id}")
            config.smartapi_id = args.smartapi_id
        if hasattr(args, "smartapi_ids") and args.smartapi_ids:
            logger.debug(f"Setting SmartAPI ids from arguments: {args.smartapi_ids}")
            # smartapi_ids from arguments is comma-separated
            if isinstance(args.smartapi_ids, str):
                config.smartapi_ids = args.smartapi_ids.split(",")
            else:
                config.smartapi_ids = args.smartapi_ids
        if hasattr(args, "smartapi_exclude_ids") and args.smartapi_exclude_ids:
            logger.debug(
                "Setting excluded SmartAPI ids from arguments: {}",
                args.smartapi_exclude_ids,
            )
            # smartapi_exclude_ids from arguments is comma-separated
            if isinstance(args.smartapi_exclude_ids, str):
                config.smartapi_exclude_ids = args.smartapi_exclude_ids.split(",")
            else:
                config.smartapi_exclude_ids = args.smartapi_exclude_ids
        if hasattr(args, "smartapi_q") and args.smartapi_q:
            logger.debug(f"Setting SmartAPI query from arguments: {args.smartapi_q}")
            config.smartapi_q = args.smartapi_q
        if hasattr(args, "api_set") and args.api_set:
            logger.debug(
                "Setting predefined SmartAPI API set from arguments: {}",
                args.api_set,
            )
            config.smartapi_api_set = args.api_set
        if hasattr(args, "server_name") and args.server_name:
            logger.debug(f"Setting MCP Server name from arguments: {args.server_name}")
            config.server_name = args.server_name
        if hasattr(args, "transport") and args.transport:
            logger.debug(
                f"Setting MCP Server transport mode from arguments: {args.transport}"
            )
            config.transport = args.transport
    # Log final configuration details
    logger.info("SmartAPI Configuration loaded")

    return config
