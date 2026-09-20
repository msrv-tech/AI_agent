# -*- coding: utf-8 -*-
"""Конфигурация HTTP-bridge и путей платформы 1С."""

import os
import sys

try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

DEFAULT_BRIDGE_URL = os.environ.get(
    "BRIDGE_URL",
    "http://192.168.2.127/fresh-unf/hs/codex-test",
)
DEFAULT_BP_BRIDGE_URL = os.environ.get(
    "BRIDGE_BP_URL",
    "http://192.168.2.127/fresh-bp-demo/hs/codex-test",
)
DEFAULT_UNF_BRIDGE_URL = os.environ.get(
    "BRIDGE_UNF_URL",
    "http://192.168.2.127/fresh-unf/hs/codex-test",
)

# Строка подключения нужна Designer/ibcmd, не HTTP-bridge.
DEFAULT_CONNECTION_STRING = os.environ.get(
    "1C_CONNECTION_STRING",
    'File="D:\\EDT_base\\КонфигурацияТест";',
)


def get_bridge_url(bridge_url: str | None = None) -> str:
    if bridge_url:
        return bridge_url.rstrip("/")
    return DEFAULT_BRIDGE_URL.rstrip("/")


def get_connection_string(connection_string: str | None = None) -> str:
    """Строка подключения для конфигуратора/ibcmd, не для автотестов агента."""
    if connection_string:
        return connection_string
    return DEFAULT_CONNECTION_STRING


def get_platform_83() -> str:
    return os.environ.get(
        "PLATFORM_83",
        r"C:\Program Files\1cv8\8.3.27.1859\bin\1cv8.exe",
    )


def get_platform_85() -> str:
    return os.environ.get(
        "PLATFORM_85",
        r"C:\Program Files\1cv8\8.5.1.1150\bin\1cv8.exe",
    )


def setup_console_encoding() -> None:
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
