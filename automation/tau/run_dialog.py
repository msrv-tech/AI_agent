# -*- coding: utf-8 -*-
"""
Создание и запуск диалога агента ИИ через HTTP-bridge.

    python automation/tau/run_dialog.py --text "Покажи всех контрагентов" --type Запрос1С
    python automation/tau/run_dialog.py --text "Создай документ" --type Agent --log-file run_log.txt
"""

import os
import sys
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_script_dir)
_repo_root = os.path.dirname(_automation_dir)
for _path in (_script_dir, _automation_dir, _repo_root):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from automation.bridge.client import run_agent_dialog
from automation.bridge.config import get_bridge_url, setup_console_encoding

DEFAULT_MAX_LOG_SIZE = 10 * 1024 * 1024


def main():
    setup_console_encoding()
    import argparse

    parser = argparse.ArgumentParser(
        description="Создание и запуск диалога агента ИИ через HTTP-bridge"
    )
    parser.add_argument("--text", "-t", required=True, help="Текст задачи для агента")
    parser.add_argument("--user", "-u", default="Администратор", help="Имя пользователя")
    parser.add_argument(
        "--type",
        choices=["Agent", "Агент", "Запрос1С", "Zapros1S"],
        default="Agent",
        help="Тип диалога: Agent (Агент) или Запрос1С",
    )
    parser.add_argument("--bridge-url", default=None, help="URL HTTP-сервиса Codex Test Bridge")
    parser.add_argument("--log-file", default=None, help="Путь к файлу для записи лога")
    parser.add_argument(
        "--log-max-size",
        type=int,
        default=DEFAULT_MAX_LOG_SIZE,
        metavar="BYTES",
        help=f"Макс. размер лог-файла в байтах, при превышении выполняется ротация (по умолчанию {DEFAULT_MAX_LOG_SIZE})",
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Подробный вывод")
    args = parser.parse_args()

    try:
        result = run_agent_dialog(
            get_bridge_url(args.bridge_url),
            args.user,
            args.text,
            args.type,
            auto_confirm=True,
        )
    except Exception as e:
        print(f"Ошибка вызова агента: {e}", file=sys.stderr)
        return 1

    success = bool(result.get("Успех"))
    log_text = result.get("Лог") or ""
    ref_str = str(result.get("СсылкаДиалога") or result.get("dialog_uuid") or "")

    print("--- Результат ---")
    print(f"Диалог: {ref_str}")
    print(f"Успех: {success}")
    print()
    print("--- Лог ---")
    print(log_text or "(пусто)")

    if args.log_file:
        try:
            log_path = os.path.abspath(args.log_file)
            if os.path.exists(log_path) and os.path.getsize(log_path) >= args.log_max_size:
                old_path = log_path + ".old"
                if os.path.exists(old_path):
                    os.remove(old_path)
                os.rename(log_path, old_path)
                if args.verbose:
                    print(f"Ротация лога: {log_path} -> {old_path}")
            session_header = (
                f"\n{'='*60}\n"
                f"run_dialog | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
                f"Диалог: {ref_str} | Успех: {success}\n"
                f"Задача: {args.text[:80]}{'...' if len(args.text) > 80 else ''}\n"
                f"{'='*60}\n"
            )
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(session_header)
                f.write(log_text or "(лог пуст)")
                f.write("\n")
            print(f"\nЛог дописан в {args.log_file}")
        except Exception as e:
            print(f"Ошибка записи в файл: {e}", file=sys.stderr)
            return 1

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
