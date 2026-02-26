# -*- coding: utf-8 -*-
"""
RAG-поиск через COM.

Вызывает ИИА_RAG_Поиск.ВыполнитьПоискПоТексту(ЗапросТекст, TopK) и выводит результаты.

Запуск (из каталога automation):
    python rag_search.py остатки склад
    python rag_search.py "запасы склад" "реализация товары"
    python rag_search.py --top 5 реализация
    python rag_search.py -c "File=\"D:\\base\";" номенклатура контрагенты
"""

import sys
import os
import json

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from com_1c import connect_to_1c, call_procedure
from com_1c.com_connector import setup_console_encoding
from com_1c.config import get_connection_string


def search_rag(conn, query: str, top_k: int = 10) -> list:
    """Выполняет RAG-поиск и возвращает список результатов."""
    json_str = call_procedure(conn, "ИИА_RAG_Поиск", "ВыполнитьПоискПоТексту", query, top_k)
    if json_str is None or not isinstance(json_str, str):
        return []
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return []


def main():
    setup_console_encoding()

    import argparse
    parser = argparse.ArgumentParser(
        description="RAG-поиск по метаданным через COM"
    )
    parser.add_argument(
        "words",
        nargs="*",
        default=[],
        help="Слова/фразы для поиска (каждый аргумент — один запрос)",
    )
    parser.add_argument(
        "--connection", "-c",
        default=None,
        help="Строка подключения к 1С",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=10,
        help="Количество результатов (по умолчанию 10)",
    )
    args = parser.parse_args()

    connection_string = get_connection_string(args.connection)
    conn = connect_to_1c(connection_string)
    if conn is None:
        print("Ошибка: не удалось подключиться к 1С.", file=sys.stderr)
        return 1

    if args.words:
        queries = args.words
    else:
        queries = ["остатки склад", "запасы склад", "реализация товары"]

    for query in queries:
        print(f"\n--- Запрос: «{query}» ---")
        results = search_rag(conn, query, args.top)
        if not results:
            print("  Результатов нет.")
            continue

        for r in results:
            rank = r.get("Rank", "")
            score = r.get("Score", 0)
            typ = r.get("Тип", "")
            name = r.get("Имя", "")
            synonym = r.get("Синоним", "")
            path = r.get("Путь", "")
            print(f"  {rank}. [{score:.1f}] {typ}.{name} ({synonym}) — {path}")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
