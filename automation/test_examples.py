# -*- coding: utf-8 -*-
"""
Тестирование примеров через COM.

Создаёт диалоги для каждого примера запроса, выполняет агента
синхронно через ИИА_ДиалогCOM. Сохраняет лог каждого диалога в отдельный
текстовый файл. По окончании отправляет уведомление в Telegram.

Запуск (из каталога automation):
    python test_examples.py
    python test_examples.py --connection "File=\"D:\\base\";"
    python test_examples.py --log-dir ./logs --verbose

Секреты Telegram в .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import sys
import os
import re
import json
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime
from pathlib import Path

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from com_1c import connect_to_1c, call_procedure, get_enum_value
from com_1c.com_connector import setup_console_encoding
from com_1c.config import get_connection_string

# Загрузка .env для Telegram
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass


# Примеры запросов (раздел "Что можно спросить?")
README_EXAMPLES = [
    {
        "id": "orders_client",
        "text": "Найди все заказы клиента 'ТехноПром' за прошлую неделю и выведи общую сумму.",
        "type": "Запрос1С",
        "description": "Поиск заказов клиента и сумма",
    },
    {
        "id": "stock_low",
        "text": "Какие товары на складе 'Основной' имеют остаток меньше 5 штук?",
        "type": "Запрос1С",
        "description": "Остатки на складе",
    },
    {
        "id": "create_receipt",
        "text": "Создай черновик приходной накладной от поставщика 'Мир Мебели' на основании счета №123.",
        "type": "Agent",
        "description": "Создание черновика приходной накладной",
    },
    {
        "id": "sales_analysis",
        "text": "Проанализируй динамику продаж за последний месяц и выдели топ-3 растущих категории.",
        "type": "Запрос1С",
        "description": "Анализ динамики продаж",
    },
]

# Тариф Gitsell: 400 руб / 1 800 000 токенов
GITSELL_RUB_PER_TOKEN = 400 / 1_800_000

# Слова подтверждения в резюме (регистронезависимо)
SUMMARY_CONFIRM_WORDS = (
    "выполнен", "успешно", "создан", "найден", "выполнена", "сформирован",
    "получен", "завершен", "завершён"
)
SUMMARY_MARKER = "=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ==="
SUMMARY_NOT_FORMED = "Резюме не сформировано"


def _get(obj, name, default=None):
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


def run_dialog(conn, text: str, dialog_type: str, user: str = "Администратор"):
    """Запускает диалог через COM и возвращает результат."""
    type_map = {"Agent": "Агент", "Агент": "Агент", "Запрос1С": "Запрос1С", "Zapros1S": "Запрос1С"}
    enum_value_name = type_map.get(dialog_type, "Запрос1С")
    enum_val = get_enum_value(conn, "ИИА_ТипДиалога", enum_value_name)
    if enum_val is None:
        raise RuntimeError(f"Не удалось получить ИИА_ТипДиалога.{enum_value_name}")

    result = call_procedure(
        conn,
        "ИИА_ДиалогCOM",
        "СоздатьДиалогИВыполнитьАгентаСинхронно",
        user,
        text,
        enum_val,
    )
    return result


def send_telegram_notification(message: str) -> bool:
    """Отправляет уведомление в Telegram. Возвращает True при успехе."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def analyze_log(log_text: str) -> dict:
    """
    Анализирует лог диалога и извлекает ключевую информацию.
    """
    analysis = {
        "has_error": False,
        "error_lines": [],
        "dsl_steps": [],
        "dsl_errors": [],
        "ai_calls": 0,
        "plan_completed": False,
        "summary_present": False,
        "summary_confirmed": False,
    }

    if not log_text:
        return analysis

    lines = log_text.split("\n")
    for line in lines:
        line_stripped = line.strip()
        # Ошибки
        if "[ОШИБКА]" in line or "Ошибка" in line or "ошибка" in line:
            analysis["has_error"] = True
            analysis["error_lines"].append(line_stripped[:200])
        # DSL шаги
        if "dsl_step" in line.lower() or "dsl_execute" in line.lower():
            analysis["dsl_steps"].append(line_stripped[:150])
        # Ошибки DSL
        if "dsl_error" in line.lower() or "dsl_fail" in line.lower():
            analysis["dsl_errors"].append(line_stripped[:200])
        # Вызовы ИИ
        if "Вызов ИИ" in line or "call_ai" in line.lower():
            analysis["ai_calls"] += 1
        # План завершён
        if "ПланЗавершен" in line or "план завершён" in line.lower():
            analysis["plan_completed"] = True
        # Summary
        if "summary" in line.lower() or "итог" in line.lower():
            analysis["summary_present"] = True

    # Дополнительный поиск RunQuery, GetMetadata и т.д.
    dsl_actions = re.findall(r"(RunQuery|GetMetadata|GetObjectFields|FindReferenceByName|CreateDocument|CreateReference)", log_text, re.I)
    analysis["dsl_actions_found"] = list(set(dsl_actions))

    # Резюме: проверка маркера и слов подтверждения
    if SUMMARY_MARKER in log_text:
        analysis["summary_present"] = True
        # Извлекаем текст резюме после маркера
        idx = log_text.find(SUMMARY_MARKER)
        summary_text = log_text[idx + len(SUMMARY_MARKER):].strip()
        # Ограничиваем до следующего блока или 500 символов
        if "\n\n" in summary_text:
            summary_text = summary_text.split("\n\n")[0]
        summary_text = summary_text[:500].lower()
        if SUMMARY_NOT_FORMED.lower() in summary_text:
            analysis["summary_confirmed"] = False
        else:
            analysis["summary_confirmed"] = any(
                w in summary_text for w in SUMMARY_CONFIRM_WORDS
            )

    return analysis


def main():
    setup_console_encoding()
    import argparse

    parser = argparse.ArgumentParser(
        description="Тестирование примеров через COM"
    )
    parser.add_argument(
        "--connection", "-c",
        default=None,
        help="Строка подключения к 1С",
    )
    parser.add_argument(
        "--log-dir",
        default=None,
        help="Каталог для сохранения логов (по умолчанию automation/logs)",
    )
    parser.add_argument(
        "--user", "-u",
        default="Администратор",
        help="Имя пользователя",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Подробный вывод",
    )
    parser.add_argument(
        "--example",
        default=None,
        help="Запустить только один пример по id (orders_client, stock_low, create_receipt, sales_analysis)",
    )
    parser.add_argument(
        "--examples",
        default=None,
        help="Запустить только указанные примеры (id через запятую: orders_client,stock_low)",
    )
    args = parser.parse_args()

    connection_string = get_connection_string(args.connection)
    log_dir = args.log_dir or os.path.join(_script_dir, "logs")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_prefix = f"examples_{timestamp}"
    run_log_dir = os.path.join(log_dir, run_prefix)
    Path(run_log_dir).mkdir(parents=True, exist_ok=True)
    report_file = os.path.join(run_log_dir, "report.json")

    examples = README_EXAMPLES
    if args.example:
        examples = [e for e in examples if e["id"] == args.example]
        if not examples:
            print(f"Ошибка: пример '{args.example}' не найден", file=sys.stderr)
            return 1
    elif args.examples:
        ids = [s.strip() for s in args.examples.split(",") if s.strip()]
        examples = [e for e in examples if e["id"] in ids]
        if not examples:
            print(f"Ошибка: примеры '{args.examples}' не найдены", file=sys.stderr)
            return 1

    print("=" * 70)
    print("Тестирование примеров (через COM)")
    print("=" * 70)

    conn = connect_to_1c(connection_string)
    if not conn:
        print("Ошибка: не удалось подключиться к 1С", file=sys.stderr)
        return 1

    results = []
    all_success = True

    for ex in examples:
        print(f"\n--- {ex['id']}: {ex['description']} ---")
        print(f"Запрос: {ex['text'][:70]}...")
        print(f"Тип: {ex['type']}")

        try:
            result = run_dialog(conn, ex["text"], ex["type"], args.user)
        except Exception as e:
            print(f"  ОШИБКА: {e}")
            log_content = f"[{ex['id']}] ИСКЛЮЧЕНИЕ: {e}\n"
            log_path = os.path.join(run_log_dir, f"{ex['id']}.txt")
            with open(log_path, "w", encoding="utf-8") as f:
                f.write(log_content)
            results.append({
                "id": ex["id"],
                "success": False,
                "passed": False,
                "usage_tokens": 0,
                "error": str(e),
                "log_file": log_path,
            })
            all_success = False
            continue

        success = _get(result, "Успех", False)
        log_text = _get(result, "Лог") or ""
        ref_str = str(_get(result, "СсылкаДиалога") or "")
        usage_tokens = int(_get(result, "UsageTokens") or 0)

        analysis = analyze_log(log_text)
        passed = success and analysis["summary_present"] and analysis["summary_confirmed"]

        status = "OK" if passed else "FAIL"
        print(f"  Результат: {status} | Диалог: {ref_str}")

        if analysis["has_error"] and analysis["error_lines"]:
            print(f"  Ошибки в логе: {len(analysis['error_lines'])}")
            if args.verbose:
                for err in analysis["error_lines"][:3]:
                    print(f"    - {err[:80]}...")

        if analysis["dsl_actions_found"]:
            print(f"  DSL-действия: {', '.join(analysis['dsl_actions_found'])}")

        # Сохранение лога в отдельный файл сразу после диалога
        log_content = (
            f"[{ex['id']}] {ex['text']}\n"
            f"Тип: {ex['type']} | Успех: {success} | Диалог: {ref_str}\n"
            f"{'='*60}\n"
            f"{log_text or '(лог пуст)'}"
        )
        log_path = os.path.join(run_log_dir, f"{ex['id']}.txt")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(log_content)
        print(f"  Лог: {log_path}")

        results.append({
            "id": ex["id"],
            "text": ex["text"],
            "type": ex["type"],
            "success": success,
            "passed": passed,
            "usage_tokens": usage_tokens,
            "dialog_ref": ref_str,
            "log_file": log_path,
            "has_error": analysis["has_error"],
            "error_count": len(analysis["error_lines"]),
            "summary_present": analysis["summary_present"],
            "summary_confirmed": analysis["summary_confirmed"],
            "dsl_actions": analysis["dsl_actions_found"],
            "ai_calls": analysis["ai_calls"],
            "plan_completed": analysis["plan_completed"],
        })

    # Сохранение отчёта
    passed_count = sum(1 for r in results if r.get("passed", False))
    total_tokens = sum(r.get("usage_tokens", 0) for r in results)
    cost_rub = round(total_tokens * GITSELL_RUB_PER_TOKEN, 2)
    all_success = all(r.get("passed", False) for r in results)
    report = {
        "timestamp": timestamp,
        "run_id": run_prefix,
        "log_dir": run_log_dir,
        "total": len(results),
        "passed_count": passed_count,
        "success_count": passed_count,  # для обратной совместимости
        "all_success": all_success,
        "total_tokens": total_tokens,
        "cost_rub": cost_rub,
        "log_files": [r.get("log_file", "") for r in results if r.get("log_file")],
        "results": results,
    }

    with open(report_file, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    # Итоговый вывод
    print("\n" + "=" * 70)
    print("ИТОГ")
    print("=" * 70)
    print(f"Пройдено: {passed_count}/{len(results)}")
    print(f"Токены: {total_tokens:,} | Стоимость: ~{cost_rub} ₽")
    print(f"Каталог логов: {run_log_dir}")
    print(f"Файлы: {len([r for r in results if r.get('log_file')])} шт.")

    if not all_success:
        print("\nПровалившиеся примеры:")
        for r in results:
            if not r.get("passed", False):
                print(f"  - {r['id']}: {r.get('error', 'нет резюме/подтверждения')}")

    # Уведомление в Telegram
    tg_ok = send_telegram_notification(
        f"<b>Тесты примеров завершены</b>\n\n"
        f"Пройдено: {passed_count}/{len(results)}\n"
        f"Токены: {total_tokens:,} | Стоимость: ~{cost_rub} ₽\n"
        f"Каталог: <code>{run_log_dir}</code>\n"
        f"{'✅ Все пройдены' if all_success else '❌ Есть провалы'}"
    )
    if tg_ok:
        print("\nУведомление отправлено в Telegram")
    elif os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_CHAT_ID"):
        print("\nНе удалось отправить уведомление в Telegram (проверьте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID)")
    else:
        print("\nTelegram: не настроен (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID в .env)")

    return 0 if all_success else 1


if __name__ == "__main__":
    sys.exit(main())
