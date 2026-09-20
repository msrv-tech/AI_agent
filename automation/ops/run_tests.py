# -*- coding: utf-8 -*-
"""
Запуск тестов ИИА через HTTP-bridge.

Перед тестами выполняется обновление БД (xml → конфигурация → UpdateDBCfg).
Флаг --skip-update пропускает обновление.

Запуск:
    python automation/ops/run_tests.py
    python automation/ops/run_tests.py --dry-run
    python automation/ops/run_tests.py --bridge-url http://192.168.2.127/fresh-unf/hs/codex-test --skip-update
"""

import sys
import os
import subprocess

# Поддержка запуска из каталога automation/ops
_script_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_script_dir)
_repo_root = os.path.dirname(_automation_dir)
for _path in (_script_dir, _automation_dir, _repo_root):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from automation.bridge.client import call_exported
from automation.bridge.config import get_bridge_url, get_connection_string, setup_console_encoding


def _get(obj, name, default=None):
    """Безопасно получает поле результата теста."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def _print_result(name, result, verbose=True):
    """Выводит результат одного теста."""
    success = _get(result, "Успех", False)
    message = _get(result, "Сообщение") or ""
    details = _get(result, "Детали")
    status = "OK" if success else "FAIL"
    print(f"[{status}] {name}: {message}")
    if verbose and details is not None:
        try:
            if hasattr(details, "Count") and hasattr(details, "Get"):
                for i in range(details.Count()):
                    print(f"      {details.Get(i)}")
            else:
                for item in details:
                    print(f"      {item}")
        except Exception:
            pass
    return success


def main():
    setup_console_encoding()
    import argparse

    parser = argparse.ArgumentParser(
        description="Запуск тестов ИИА через HTTP-bridge"
    )
    parser.add_argument(
        "--bridge-url",
        default=None,
        help="URL HTTP-сервиса Codex Test Bridge",
    )
    parser.add_argument(
        "--connection", "-c",
        default=None,
        help="Строка подключения к 1С только для update_1c.py (конфигуратор)",
    )
    parser.add_argument(
        "--test", "-t",
        default=None,
        help="Запустить один тест по имени (напр. ТестRunQuery)",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод деталей",
    )
    parser.add_argument(
        "--with-ai",
        action="store_true",
        help="Включить тесты с реальным вызовом ИИ (медленные)",
    )
    parser.add_argument(
        "--ai-only",
        action="store_true",
        help="Только боевые тесты с ИИ (без бесплатных)",
    )
    parser.add_argument(
        "--dry-run", "-d",
        action="store_true",
        help="Тесты холостого хода (mock-ответы, без вызова ИИ)",
    )
    parser.add_argument(
        "--skip-update",
        action="store_true",
        help="Пропустить обновление БД перед тестами",
    )
    args = parser.parse_args()

    connection_string = get_connection_string(args.connection)
    if args.connection:
        os.environ["1C_CONNECTION_STRING"] = connection_string
    bridge_url = get_bridge_url(args.bridge_url)

    # Предварительное обновление БД (xml → конфигурация → UpdateDBCfg)
    if not args.skip_update:
        update_script = os.path.join(_script_dir, "update_1c.py")
        try:
            result = subprocess.run(
                [sys.executable, update_script, "--skip-run-client"],
                cwd=_script_dir,
                timeout=120,
                env={**os.environ, "1C_CONNECTION_STRING": connection_string},
            )
            if result.returncode != 0:
                print("Ошибка: обновление БД завершилось с ошибкой", file=sys.stderr)
                return 1
        except subprocess.TimeoutExpired:
            print("Ошибка: превышено время ожидания обновления БД", file=sys.stderr)
            return 1
        except Exception as e:
            print(f"Ошибка при обновлении БД: {e}", file=sys.stderr)
            return 1

    if args.test:
        try:
            result = call_exported(bridge_url, "ИИА_Тесты", args.test, timeout=600)
        except Exception as e:
            print(f"Ошибка вызова ИИА_Тесты.{args.test}: {e}", file=sys.stderr)
            return 1

        if result is None:
            print("Ошибка: процедура вернула пустой результат", file=sys.stderr)
            return 1

        success = _print_result(args.test, result, verbose=True)
        return 0 if success else 1
    else:
        # Набор тестов: по умолчанию бесплатные, --dry-run холостой ход, --with-ai все, --ai-only только ИИ
        if args.dry_run:
            proc_name = "ЗапуститьТестыХолостойХод"
        elif args.ai_only:
            proc_name = "ЗапуститьТестыСИИ"
        elif args.with_ai:
            proc_name = "ЗапуститьВсеТесты"
        else:
            proc_name = "ЗапуститьБесплатныеТесты"
        try:
            results = call_exported(bridge_url, "ИИА_Тесты", proc_name, timeout=1800)
        except Exception as e:
            print(f"Ошибка вызова ИИА_Тесты.{proc_name}: {e}", file=sys.stderr)
            return 1

        if args.dry_run:
            print("--- Тесты холостого хода (mock) ---")
        elif args.ai_only:
            print("--- Боевые тесты с ИИ ---")
        elif args.with_ai:
            print("--- Тесты (включая с вызовом ИИ) ---")
        else:
            print("--- Бесплатные тесты ---")

        if results is None:
            print("Ошибка: процедура вернула пустой результат", file=sys.stderr)
            return 1

        all_ok = True
        try:
            rows = list(results) if isinstance(results, list) else []
            if not rows and results is not None and not isinstance(results, list):
                print(f"Ошибка чтения результатов: неожиданный тип {type(results)}", file=sys.stderr)
                return 1
            for i, r in enumerate(rows):
                name = _get(r, "ИмяТеста", f"Тест{i+1}")
                ok = _print_result(name, r, verbose=args.verbose)
                if not ok:
                    all_ok = False
        except Exception as e:
            print(f"Ошибка чтения результатов: {e}", file=sys.stderr)
            return 1

        print()
        print("--- Итого ---")
        print(f"Результат: {'Все тесты пройдены' if all_ok else 'Есть провалы'}")
        return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
