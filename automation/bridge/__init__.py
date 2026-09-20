# -*- coding: utf-8 -*-
"""HTTP-bridge клиент к 1С вместо COM."""

from .client import (
    call_exported,
    execute_bsl,
    prepare_query1c_dialog,
    query,
    run_agent_dialog,
)
from .config import get_bridge_url, get_platform_83, get_platform_85, setup_console_encoding

__all__ = [
    "call_exported",
    "execute_bsl",
    "get_bridge_url",
    "get_platform_83",
    "get_platform_85",
    "prepare_query1c_dialog",
    "query",
    "run_agent_dialog",
    "setup_console_encoding",
]
