# -*- coding: utf-8 -*-
"""
RAG-поиск через HTTP-bridge.

Вызывает ИИА_RAG_Поиск.ВыполнитьПоискПоТексту(ЗапросТекст, TopK) и выводит результаты.
С флагом --fields вызывает ВыполнитьПоискПоТекстуСПолями.

    python automation/rag/rag_search.py остатки склад
    python automation/rag/rag_search.py --fields "продажи реализация"
"""

import sys
import os
import json

_script_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_script_dir)
_repo_root = os.path.dirname(_automation_dir)
for _path in (_script_dir, _automation_dir, _repo_root):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from automation.bridge.client import call_exported
from automation.bridge.config import get_bridge_url, setup_console_encoding


def search_rag(bridge_url: str, query: str, top_k: int = 10, with_fields: bool = False) -> list:
    """Выполняет RAG-поиск и возвращает список результатов."""
    proc = "ВыполнитьПоискПоТекстуСПолями" if with_fields else "ВыполнитьПоискПоТексту"
    json_str = call_exported(bridge_url, "ИИА_RAG_Поиск", proc, '"' + query.replace('"', '""') + '"', str(top_k))
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
        description="RAG-поиск по метаданным через HTTP-bridge"
    )
    parser.add_argument(
        "words",
        nargs="*",
        default=[],
        help="Слова/фразы для поиска (каждый аргумент — один запрос)",
    )
    parser.add_argument(
        "--bridge-url",
        default=None,
        help="URL HTTP-сервиса Codex Test Bridge",
    )
    parser.add_argument(
        "--top", "-n",
        type=int,
        default=10,
        help="Количество результатов (по умолчанию 10)",
    )
    parser.add_argument(
        "--fields", "-f",
        action="store_true",
        help="Выводить поля (реквизиты/измерения/ресурсы) для каждого результата — для анализа RAG",
    )
    args = parser.parse_args()

    bridge_url = get_bridge_url(args.bridge_url)

    if args.words:
        queries = args.words
    else:
        queries = ["остатки склад", "запасы склад", "реализация товары"]

    for query in queries:
        print(f"\n--- Запрос: «{query}» ---")
        results = search_rag(bridge_url, query, args.top, with_fields=args.fields)
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
            if args.fields:
                fields = r.get("Поля", "")
                if fields:
                    # Ограничиваем вывод полей для читаемости
                    fields_preview = fields[:400] + ("..." if len(fields) > 400 else "")
                    print(f"      Поля: {fields_preview}")
                else:
                    print("      Поля: (нет)")

    print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
