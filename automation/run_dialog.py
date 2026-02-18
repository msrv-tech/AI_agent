# -*- coding: utf-8 -*-
"""
Создание и запуск диалога агента ИИ через COM (без открытия 1С).

Запуск (из каталога automation):
    python run_dialog.py --text "Покажи всех контрагентов" --type Запрос1С
    python run_dialog.py --text "Создай документ" --type Agent --log-file run_log.txt
    python run_dialog.py -t "Задача" -u "Администратор" --connection "File=\"D:\\base\";"
"""

import sys
import os

# Поддержка запуска из каталога automation
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from com_1c import connect_to_1c, call_procedure, get_enum_value
from com_1c.com_connector import setup_console_encoding
from com_1c.config import get_connection_string


def main():
    setup_console_encoding()
    import argparse

    parser = argparse.ArgumentParser(
        description="Создание и запуск диалога агента ИИ через COM (без GUI 1С)"
    )
    parser.add_argument(
        "--text", "-t",
        required=True,
        help="Текст задачи для агента",
    )
    parser.add_argument(
        "--user", "-u",
        default="Администратор",
        help="Имя пользователя (по умолчанию: Администратор)",
    )
    parser.add_argument(
        "--type",
        choices=["Agent", "Агент", "Запрос1С", "Zapros1S"],
        default="Agent",
        help="Тип диалога: Agent (Агент) или Запрос1С (по умолчанию: Agent)",
    )
    parser.add_argument(
        "--connection", "-c",
        default=None,
        help="Строка подключения к 1С",
    )
    parser.add_argument(
        "--log-file",
        default=None,
        help="Путь к файлу для записи лога (опционально)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод",
    )
    args = parser.parse_args()

    connection_string = get_connection_string(args.connection)
    conn = connect_to_1c(connection_string)
    if not conn:
        return 1

    # Маппинг типа на имя значения перечисления ИИА_ТипДиалога
    type_map = {
        "Agent": "Агент",
        "Агент": "Агент",
        "Запрос1С": "Запрос1С",
        "Zapros1S": "Запрос1С",
    }
    enum_value_name = type_map.get(args.type, "Агент")

    enum_val = get_enum_value(conn, "ИИА_ТипДиалога", enum_value_name)
    if enum_val is None:
        print(f"Ошибка: не удалось получить перечисление ИИА_ТипДиалога.{enum_value_name}", file=sys.stderr)
        return 1

    try:
        result = call_procedure(
            conn,
            "ИИА_ДиалогCOM",
            "СоздатьДиалогИВыполнитьАгентаСинхронно",
            args.user,
            args.text,
            enum_val,
        )
    except Exception as e:
        print(f"Ошибка вызова ИИА_ДиалогCOM: {e}", file=sys.stderr)
        return 1

    if result is None:
        print("Ошибка: процедура вернула пустой результат", file=sys.stderr)
        return 1

    # Получаем поля из COM-структуры (result — объект 1С с полями Успех, Лог, СсылкаДиалога)
    def _get(obj, name, default=None):
        try:
            return getattr(obj, name, default)
        except Exception:
            return default

    success = _get(result, "Успех", False)
    log_text = _get(result, "Лог") or ""
    ref_obj = _get(result, "СсылкаДиалога")
    ref_str = str(ref_obj) if ref_obj is not None else ""

    print("--- Результат ---")
    print(f"Диалог: {ref_str}")
    print(f"Успех: {success}")
    print()
    print("--- Лог ---")
    print(log_text or "(пусто)")

    if args.log_file and log_text:
        try:
            with open(args.log_file, "a", encoding="utf-8") as f:
                f.write("\n=== run_dialog ===\n")
                f.write(log_text)
                f.write("\n")
            print(f"\nЛог дописан в {args.log_file}")
        except Exception as e:
            print(f"Ошибка записи в файл: {e}", file=sys.stderr)
            return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
