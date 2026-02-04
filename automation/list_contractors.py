# -*- coding: utf-8 -*-
"""
Подключение к 1С через COM и вывод всех контрагентов (Справочник.Контрагенты).

Запуск (из каталога automation, от имени администратора):
    python list_contractors.py
    python list_contractors.py --json
    python list_contractors.py --connection "File=\"D:\base\";"
"""

import sys
import json
import os

# Поддержка запуска из каталога automation (com_1c рядом со скриптом)
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from com_1c import connect_to_1c, execute_query
from com_1c.config import get_connection_string


def main():
    import argparse
    parser = argparse.ArgumentParser(description="Вывод всех контрагентов из 1С через COM")
    parser.add_argument("--connection", "-c", default=None, help="Строка подключения к 1С")
    parser.add_argument("--json", action="store_true", help="Вывести JSON")
    parser.add_argument("--limit", "-n", type=int, default=None, help="Максимум записей (по умолчанию все)")
    args = parser.parse_args()

    connection_string = get_connection_string(args.connection)
    conn = connect_to_1c(connection_string)
    if not conn:
        return 1

    first_n = f"ПЕРВЫЕ {args.limit} " if args.limit else ""
    query_text = f"""
    ВЫБРАТЬ {first_n}
        Контрагенты.Ссылка КАК Ссылка,
        Контрагенты.Наименование КАК Наименование
    ИЗ
        Справочник.Контрагенты КАК Контрагенты
    УПОРЯДОЧИТЬ ПО
        Наименование
    """

    columns = ["Ссылка", "Наименование"]
    try:
        rows = execute_query(conn, query_text, columns)
    except Exception as e:
        print(f"Ошибка запроса: {e}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print(f"Контрагентов: {len(rows)}\n")
        for i, row in enumerate(rows, 1):
            ref = row.get("Ссылка", "")
            name = row.get("Наименование", "")
            print(f"  {i}. {name}  [{ref}]")
    return 0


if __name__ == "__main__":
    sys.exit(main())
