# -*- coding: utf-8 -*-
"""
Пакет для работы с базой 1С через COM.

Использование:
    from com_1c import connect_to_1c, execute_query

    conn = connect_to_1c('File="C:\\path\\to\\base";')
    rows = execute_query(conn, "ВЫБРАТЬ 1 КАК Номер", ["Номер"])
"""

from .com_connector import (
    connect_to_1c,
    get_com_connector,
    resolve_connection_string,
    create_query,
    execute_query,
    safe_getattr,
    call_if_callable,
    setup_console_encoding,
    get_enum_value,
    call_procedure,
    structure_to_dict,
)

__all__ = [
    "connect_to_1c",
    "get_com_connector",
    "resolve_connection_string",
    "create_query",
    "execute_query",
    "safe_getattr",
    "call_if_callable",
    "setup_console_encoding",
    "get_enum_value",
    "call_procedure",
    "structure_to_dict",
]
