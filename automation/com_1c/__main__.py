# -*- coding: utf-8 -*-
r"""
Точка входа для запуска операций с 1С через COM из командной строки.

Примеры:
    python -m com_1c --connection "File=\"D:\base\";" --query "ВЫБРАТЬ 1 КАК Х"
    python -m com_1c --query "ВЫБРАТЬ ПЕРВЫЕ 5 Ссылка, Наименование ИЗ Справочник.Контрагенты"
    set 1C_CONNECTION_STRING=File="D:\EDT_base\КонфигурацияТест"
    python -m com_1c --query "ВЫБРАТЬ 1 КАК Номер" --columns Номер
"""

import argparse
import json
import sys


from .com_connector import connect_to_1c, execute_query, set_verbose, setup_console_encoding
from .config import get_connection_string


def _parse_columns(columns_arg: str) -> list:
    if not columns_arg:
        return []
    return [c.strip() for c in columns_arg.split(",") if c.strip()]


def main() -> int:
    setup_console_encoding()
    parser = argparse.ArgumentParser(
        description="Выполнение запроса к базе 1С через COM"
    )
    parser.add_argument(
        "--connection",
        "-c",
        default=None,
        help="Строка подключения к 1С (или 1C_CONNECTION_STRING)",
    )
    parser.add_argument(
        "--query",
        "-q",
        default=None,
        help="Текст запроса на языке запросов 1С",
    )
    parser.add_argument(
        "--columns",
        default=None,
        help="Имена колонок через запятую (для вывода). Если не заданы, вывод в одну колонку «Значение» не поддерживается — укажите колонки.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Вывести результат в JSON",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Подробный вывод",
    )
    args = parser.parse_args()

    set_verbose(bool(args.verbose))
    connection_string = get_connection_string(args.connection)

    if not args.query:
        print("Укажите запрос: --query \"ВЫБРАТЬ ...\"", file=sys.stderr)
        return 1

    conn = connect_to_1c(connection_string)
    if conn is None:
        return 1

    columns = _parse_columns(args.columns)
    if not columns:
        print(
            "Укажите имена колонок: --columns \"Колонка1,Колонка2\" (из псевдонимов ВЫБРАТЬ ... КАК Колонка1)",
            file=sys.stderr,
        )
        return 1

    try:
        rows = execute_query(conn, args.query, columns)
    except Exception as e:
        print(f"Ошибка выполнения запроса: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        for row in rows:
            print("\t".join(str(row.get(c, "")) for c in columns))
    return 0


if __name__ == "__main__":
    sys.exit(main())
