# -*- coding: utf-8 -*-
"""
CLI цикл: тест → анализ → согласование в Telegram → правки → повтор.

Запуск (из каталога automation или корня проекта):
    python test_fix_cycle.py --run              # полный цикл
    python test_fix_cycle.py --run-tests-only  # только тесты
    python test_fix_cycle.py --analyze readme_20250227_143000
    python test_fix_cycle.py --apply readme_20250227_143000 --approve 1,3

Правки не коммитятся и не пушятся — остаются для ручного просмотра.
"""

import sys
import os
import re
import json
import subprocess
import shutil
from pathlib import Path

_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)
_root = os.path.dirname(_script_dir)

try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

from com_1c.com_connector import setup_console_encoding
from test_readme_examples import (
    README_EXAMPLES,
    GITSELL_RUB_PER_TOKEN,
    send_telegram_notification,
)
from telegram_approval import send_proposals, wait_for_approval, send_message

# Таймаут для Cursor CLI (может зависать после завершения)
CURSOR_ANALYZE_TIMEOUT = 900  # 15 мин
CURSOR_APPLY_TIMEOUT = 600    # 10 мин
APPROVAL_TIMEOUT = 86400     # 24 ч


def _log_dir():
    return os.path.join(_script_dir, "logs")


def _cycle_state_path():
    return os.path.join(_log_dir(), "cycle_state.json")


def _find_agent_cmd():
    """Возвращает (путь к agent, "agent") или (путь к cursor, "cursor_agent")."""
    path = shutil.which("agent")
    if path:
        return path, "agent"
    local = os.environ.get("LOCALAPPDATA", "")
    for name in ("agent.exe", "agent.cmd", "cursor-agent.exe"):
        p = os.path.join(local, "cursor-agent", name)
        if os.path.isfile(p):
            return p, "agent"
    path = shutil.which("cursor")
    if path:
        return path, "cursor_agent"
    p = os.path.join(local, "Programs", "cursor", "resources", "app", "bin", "cursor.cmd")
    if os.path.isfile(p):
        return p, "cursor_agent"
    return None, None


def load_cycle_state():
    p = Path(_cycle_state_path())
    if not p.exists():
        return {"passed_ids": [], "total_tokens": 0, "total_cost_rub": 0}
    try:
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"passed_ids": [], "total_tokens": 0, "total_cost_rub": 0}


def save_cycle_state(state):
    Path(_log_dir()).mkdir(parents=True, exist_ok=True)
    with open(_cycle_state_path(), "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)


def run_tests(examples_arg=None):
    """Запускает test_readme_examples.py. Возвращает (returncode, run_id, report_path)."""
    cmd = [sys.executable, os.path.join(_script_dir, "test_readme_examples.py")]
    if examples_arg:
        cmd.extend(["--examples", examples_arg])
    env = {**os.environ, "PYTHONPATH": _script_dir}
    result = subprocess.run(
        cmd,
        cwd=_script_dir,
        env=env,
        timeout=7200,  # 2 ч макс на тесты
    )
    # Ищем последний report.json
    log_dir = Path(_log_dir())
    reports = sorted(log_dir.glob("readme_*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    run_id = reports[0].parent.name if reports else None
    report_path = str(reports[0]) if reports else None
    return result.returncode, run_id, report_path


def load_report(report_path):
    with open(report_path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_failed_and_passed(report):
    failed = []
    passed = []
    for r in report.get("results", []):
        if r.get("passed", False):
            passed.append(r["id"])
        else:
            failed.append(r["id"])
    return failed, passed


def run_cursor_analyze(run_id, report_path, log_dir):
    """Запускает Cursor CLI для анализа логов. Возвращает stdout."""
    prompt = f"""Проанализируй логи тестов в каталоге {log_dir}.
Файл report.json: {report_path}
Тест провален, если в логе нет блока "=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ===" или в тексте резюме нет слов подтверждения (выполнен, успешно, создан, найден и т.п.).
Предложи правки BSL-кода в xml/ для исправления ошибок.
Выведи предложения в формате:

PROPOSAL 1
FILE: xml/CommonModules/ИИА_DSL/Ext/Module.bsl
DESCRIPTION: описание правки
PATCH:
<<<<<<
unified diff здесь
>>>>>>
END_PROPOSAL

PROPOSAL 2
...
END_PROPOSAL
"""
    agent_path, kind = _find_agent_cmd()
    if not agent_path:
        return "[ERROR] Cursor Agent CLI не найден. Запустите: python check_cursor_cli.py"
    if kind == "agent":
        cmd = [agent_path, "--trust", "-f", "--workspace", _root, "-p", prompt,
               "--model", "Composer 1.5", "--mode", "ask", "--output-format", "text"]
    else:
        cmd = [agent_path, "agent", "--trust", "-f", "--workspace", _root, "-p", prompt,
               "--model", "Composer 1.5", "--mode", "ask", "--output-format", "text"]
    try:
        result = subprocess.run(
            cmd,
            cwd=_root,
            capture_output=True,
            timeout=CURSOR_ANALYZE_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return (result.stdout or "") + "\n" + (result.stderr or "")
    except subprocess.TimeoutExpired:
        return "[TIMEOUT] Cursor CLI превысил время ожидания"
    except FileNotFoundError:
        return "[ERROR] cursor CLI не найден. Установите: irm 'https://cursor.com/install?win32=true' | iex"
    except Exception as e:
        return f"[ERROR] {e}"


def parse_proposals(text):
    """Парсит вывод Cursor в список предложений."""
    proposals = []
    pattern = re.compile(
        r"PROPOSAL\s+(\d+)\s*\n"
        r"FILE:\s*(.+?)\n"
        r"DESCRIPTION:\s*(.+?)\n"
        r"PATCH:\s*\n<<<<<<\n(.*?)>>>>>>\s*\n"
        r"END_PROPOSAL",
        re.DOTALL | re.IGNORECASE
    )
    for m in pattern.finditer(text):
        proposals.append({
            "index": int(m.group(1)),
            "file": m.group(2).strip(),
            "description": m.group(3).strip()[:200],
            "patch": m.group(4).strip(),
        })
    # Упрощённый парсинг, если формат немного другой
    if not proposals:
        parts = re.split(r"PROPOSAL\s+\d+", text, flags=re.I)
        for i, part in enumerate(parts[1:], 1):
            file_m = re.search(r"FILE:\s*(.+?)(?:\n|$)", part)
            desc_m = re.search(r"DESCRIPTION:\s*(.+?)(?:\n|$)", part)
            patch_m = re.search(r"<<<<<<\n(.*?)>>>>>", part, re.DOTALL)
            if file_m:
                proposals.append({
                    "index": i,
                    "file": file_m.group(1).strip(),
                    "description": (desc_m.group(1) if desc_m else "").strip()[:200],
                    "patch": (patch_m.group(1) if patch_m else "").strip(),
                })
    return proposals


def run_cursor_apply(proposals, approved_indices, proposals_path, comment: str = ""):
    """Применяет одобренные предложения через Cursor CLI."""
    if not approved_indices:
        approved_indices = list(range(1, len(proposals) + 1))
    selected = [p for p in proposals if p["index"] in approved_indices]
    if not selected:
        return False, "Нет предложений для применения"
    prompt = f"""Примени следующие правки из файла {proposals_path}.
Номера одобренных предложений: {approved_indices}
Не коммить и не пушить — оставь изменения в рабочей директории для ручного просмотра.
"""
    if comment:
        prompt += f"\nКомментарий пользователя (учесть при применении): {comment}"
    agent_path, kind = _find_agent_cmd()
    if not agent_path:
        return False, "Cursor Agent CLI не найден. Запустите: python check_cursor_cli.py"
    if kind == "agent":
        cmd = [agent_path, "--trust", "--workspace", _root, "-p", prompt, "--model", "Composer 1.5"]
    else:
        cmd = [agent_path, "agent", "--trust", "--workspace", _root, "-p", prompt, "--model", "Composer 1.5"]
    try:
        result = subprocess.run(
            cmd,
            cwd=_root,
            capture_output=True,
            timeout=CURSOR_APPLY_TIMEOUT,
            text=True,
        )
        return result.returncode == 0, result.stdout or result.stderr or ""
    except Exception as e:
        return False, str(e)


def cmd_run(args):
    """Полный цикл: тесты → анализ → TG → ожидание → правки → повтор."""
    state = load_cycle_state()
    passed_ids = set(state.get("passed_ids", []))
    total_tokens = state.get("total_tokens", 0)
    total_cost_rub = state.get("total_cost_rub", 0)
    all_ids = {e["id"] for e in README_EXAMPLES}

    while True:
        examples_arg = None
        if passed_ids:
            to_run = sorted(all_ids - passed_ids)
            if not to_run:
                send_telegram_notification(
                    f"<b>Все тесты пройдены</b>\n\n"
                    f"Токены за цикл: {total_tokens:,} | Стоимость: ~{total_cost_rub} ₽"
                )
                print("Все тесты пройдены.")
                return 0
            examples_arg = ",".join(to_run)
            print(f"Запуск только провалившихся: {examples_arg}")

        print("Запуск тестов...")
        rc, run_id, report_path = run_tests(examples_arg)
        if report_path is None:
            print("Ошибка: report.json не найден", file=sys.stderr)
            return 1

        report = load_report(report_path)
        failed, newly_passed = get_failed_and_passed(report)
        passed_ids.update(newly_passed)
        run_tokens = report.get("total_tokens", 0)
        run_cost = report.get("cost_rub", 0)
        total_tokens += run_tokens
        total_cost_rub += run_cost
        state["passed_ids"] = sorted(passed_ids)
        state["total_tokens"] = total_tokens
        state["total_cost_rub"] = round(total_cost_rub, 2)
        state["last_run_id"] = run_id
        save_cycle_state(state)

        if not failed:
            send_telegram_notification(
                f"<b>Все тесты пройдены</b>\n\n"
                f"Токены: {total_tokens:,} | Стоимость: ~{total_cost_rub} ₽\n"
                f"Каталог: <code>{report_path}</code>"
            )
            print("Все тесты пройдены.")
            return 0

        # Анализ провалов
        log_dir = os.path.dirname(report_path)
        print("Анализ логов через Cursor CLI...")
        output = run_cursor_analyze(run_id, report_path, log_dir)
        proposals = parse_proposals(output)
        proposals_path = os.path.join(log_dir, f"proposals_{run_id}.json")
        with open(proposals_path, "w", encoding="utf-8") as f:
            json.dump({"proposals": proposals, "raw_output": output[:5000]}, f, ensure_ascii=False, indent=2)

        if not proposals:
            print("Предложения не получены. Raw output:", output[:500])
            send_telegram_notification(
                f"<b>Анализ не дал предложений</b>\n\n"
                f"Run: {run_id}\nПровалы: {', '.join(failed)}\n"
                f"Проверьте логи: {log_dir}"
            )
            return 1

        # Отправка в Telegram
        send_proposals(
            run_id=run_id,
            proposals=proposals,
            total_tokens=total_tokens,
            cost_rub=round(total_cost_rub, 2),
            failed_ids=failed,
        )
        print("Ожидание одобрения в Telegram (ответьте или нажмите кнопку)...")
        action, approved, comment = wait_for_approval(timeout_sec=APPROVAL_TIMEOUT)
        if action == "reject":
            print("Правки отклонены.")
            return 1
        if action == "timeout":
            print("Таймаут ожидания одобрения.")
            return 1
        approved_indices = approved if action == "approve_partial" else []
        if action == "approve_all":
            approved_indices = [p["index"] for p in proposals]
        if comment:
            print(f"Комментарий: {comment}")

        # Применение
        print("Применение правок через Cursor CLI...")
        ok, msg = run_cursor_apply(proposals, approved_indices, proposals_path, comment)
        if not ok:
            print(f"Ошибка применения: {msg}", file=sys.stderr)
            send_telegram_notification(f"<b>Ошибка применения правок</b>\n\n<pre>{msg[:500]}</pre>")
            return 1
        print("Правки применены (не запушены). Повторный запуск тестов...")


def cmd_run_tests_only(args):
    """Только запуск тестов."""
    rc, run_id, report_path = run_tests()
    print(f"Run ID: {run_id}, Report: {report_path}")
    return rc


def cmd_analyze(args):
    """Анализ готового прогона."""
    run_id = args.analyze
    report_path = os.path.join(_log_dir(), run_id, "report.json")
    if not os.path.isfile(report_path):
        report_path = os.path.join(_log_dir(), run_id + os.sep + "report.json")
    if not os.path.isfile(report_path):
        # try parent of report
        for p in Path(_log_dir()).glob(f"{run_id}/report.json"):
            report_path = str(p)
            break
        else:
            print(f"Report не найден: {run_id}", file=sys.stderr)
            return 1
    log_dir = os.path.dirname(report_path)
    report = load_report(report_path)
    failed, _ = get_failed_and_passed(report)
    if not failed:
        print("Все тесты пройдены, анализ не требуется.")
        return 0
    print("Анализ через Cursor CLI...")
    output = run_cursor_analyze(run_id, report_path, log_dir)
    proposals = parse_proposals(output)
    out_path = os.path.join(log_dir, f"proposals_{run_id}.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"proposals": proposals, "raw_output": output[:5000]}, f, ensure_ascii=False, indent=2)
    print(f"Предложений: {len(proposals)}, сохранено в {out_path}")
    return 0


def cmd_apply(args):
    """Применить одобренные предложения и перезапустить тесты."""
    run_id = args.apply
    approved = [int(x.strip()) for x in args.approve.split(",") if x.strip()]
    proposals_path = os.path.join(_log_dir(), run_id, f"proposals_{run_id}.json")
    if not os.path.isfile(proposals_path):
        for p in Path(_log_dir()).glob(f"{run_id}/proposals_*.json"):
            proposals_path = str(p)
            break
        else:
            print(f"Proposals не найден для {run_id}. Сначала выполните --analyze.", file=sys.stderr)
            return 1
    with open(proposals_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    proposals = data.get("proposals", [])
    if not proposals:
        print("Нет предложений для применения.", file=sys.stderr)
        return 1
    ok, msg = run_cursor_apply(proposals, approved, proposals_path)
    if not ok:
        print(f"Ошибка: {msg}", file=sys.stderr)
        return 1
    print("Правки применены. Запуск тестов...")
    rc, _, _ = run_tests()
    return rc


def main():
    setup_console_encoding()
    import argparse
    parser = argparse.ArgumentParser(description="CLI цикл: тест - анализ - согласование - правки")
    parser.add_argument("--run", "-r", action="store_true", help="Полный цикл (тесты - анализ - TG - правки - повтор)")
    parser.add_argument("--run-tests-only", action="store_true", help="Только запуск тестов")
    parser.add_argument("--analyze", metavar="RUN_ID", help="Анализ готового прогона (например readme_20250227_143000)")
    parser.add_argument("--apply", metavar="RUN_ID", help="Применить одобренные предложения")
    parser.add_argument("--approve", help="Номера предложений через запятую: 1,3 (с --apply)")
    args = parser.parse_args()
    if args.run:
        return cmd_run(args)
    if args.run_tests_only:
        return cmd_run_tests_only(args)
    if args.analyze:
        return cmd_analyze(args)
    if args.apply:
        if not args.approve:
            print("С --apply укажите --approve 1,2,3", file=sys.stderr)
            return 1
        return cmd_apply(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
