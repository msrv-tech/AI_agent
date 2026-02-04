# -*- coding: utf-8 -*-
"""
Конфигурация подключения к 1С для запуска через COM.

Строка подключения берётся из переменной окружения 1C_CONNECTION_STRING
или из файла .env в корне проекта. Та же переменная используется скриптами
сборки. Можно переопределить через параметр --connection в CLI.
"""

import os

# Загрузка .env из корня репозитория (если есть)
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

# Та же строка по умолчанию, что и в скриптах сборки (если env не задан)
DEFAULT_CONNECTION_STRING = os.environ.get(
    "1C_CONNECTION_STRING",
    'File="D:\\EDT_base\\КонфигурацияТест";',
)


def get_connection_string(connection_string: str = None) -> str:
    """Возвращает строку подключения: переданную или из окружения/по умолчанию."""
    if connection_string:
        return connection_string
    return DEFAULT_CONNECTION_STRING
