# -*- coding: utf-8 -*-
"""
CLI цикл: тест → анализ → согласование в Telegram → правки → повтор.

Запуск (из каталога automation или корня проекта):
    python long_fix_telegram.py --run              # полный цикл (обновление БД - тесты - анализ - TG - правки)
    python long_fix_telegram.py --run --skip-update # без обновления БД
    python long_fix_telegram.py --run-from examples_20260227_045200  # от существующего прогона
    python long_fix_telegram.py --run-tests-only   # только тесты
    python long_fix_telegram.py --analyze examples_20250227_143000
    python long_fix_telegram.py --apply examples_20250227_143000

Правки не коммитятся и не пушятся — остаются для ручного просмотра.
"""

import sys
import os
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
from test_examples import (
    README_EXAMPLES,
    GITSELL_RUB_PER_TOKEN,
    send_telegram_notification,
)
from telegram_approval import send_raw_analysis, wait_for_approval, send_message

# Таймаут для Cursor CLI (может зависать после завершения)
CURSOR_ANALYZE_TIMEOUT = 900  # 15 мин
CURSOR_APPLY_TIMEOUT = 600    # 10 мин
APPROVAL_TIMEOUT = 86400     # 24 ч


def _log_dir():
    return os.path.join(_script_dir, "logs")


def _cycle_state_path():
    return os.path.join(_log_dir(), "cycle_state.json")


def _find_agent_cmd(prefer_cursor: bool = True):
    """
    Возвращает (путь, "agent"|"cursor_agent").
    prefer_cursor=True — сначала cursor agent (полный IDE-агент), иначе standalone agent.
    """
    local = os.environ.get("LOCALAPPDATA", "")
    cursor_cmd = os.path.join(local, "Programs", "cursor", "resources", "app", "bin", "cursor.cmd")
    cursor_path = shutil.which("cursor") or (cursor_cmd if os.path.isfile(cursor_cmd) else None)
    agent_path = shutil.which("agent")
    if not agent_path:
        for name in ("agent.exe", "agent.cmd", "cursor-agent.exe"):
            p = os.path.join(local, "cursor-agent", name)
            if os.path.isfile(p):
                agent_path = p
                break
    if prefer_cursor and cursor_path:
        return cursor_path, "cursor_agent"
    if agent_path:
        return agent_path, "agent"
    if cursor_path:
        return cursor_path, "cursor_agent"
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


def run_update_1c():
    """Обновляет расширение и БД (xml → конфигурация → UpdateDBCfg). Возвращает True при успехе."""
    update_script = os.path.join(_script_dir, "update_1c.py")
    try:
        r = subprocess.run(
            [sys.executable, update_script, "--skip-run-client"],
            cwd=_script_dir,
            timeout=180,
            env={**os.environ},
        )
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, Exception):
        return False


def run_tests(examples_arg=None):
    """Запускает test_examples.py. Возвращает (returncode, run_id, report_path)."""
    cmd = [sys.executable, os.path.join(_script_dir, "test_examples.py")]
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
    reports = sorted(log_dir.glob("*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
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

КРИТИЧЕСКИ ВАЖНО: Выведи ТОЛЬКО предложения правок в указанном формате. Без markdown, без таблиц, без вступления.
Каждое предложение — конкретная правка BSL-кода с unified diff.

Формат (соблюдай точно):

PROPOSAL 1
FILE: xml/CommonModules/ИИА_DSL/Ext/Module.bsl
DESCRIPTION: краткое описание правки
PATCH:
<<<<<<
--- a/Module.bsl
+++ b/Module.bsl
@@ -100,7 +100,7 @@
- старая строка
+ новая строка
>>>>>>
END_PROPOSAL

PROPOSAL 2
FILE: путь/к/файлу.bsl
DESCRIPTION: описание
PATCH:
<<<<<<
unified diff
>>>>>>
END_PROPOSAL

Начни сразу с PROPOSAL 1. Минимум 1 предложение на каждый провалившийся тест."""
    agent_path, kind = _find_agent_cmd(prefer_cursor=False)
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


def _get_git_status() -> str:
    """Возвращает git status --short для отправки в Telegram."""
    try:
        r = subprocess.run(
            ["git", "status", "--short"],
            cwd=_root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
        return ""
    except Exception:
        return ""


def _print_git_status():
    """Выводит git status после применения правок."""
    s = _get_git_status()
    if s:
        print("Изменённые файлы (git status):")
        print(s)
    else:
        print("(git: изменений нет)")


def run_cursor_apply_from_analysis(analysis_path: str, comment: str = ""):
    """Применяет правки по сырому анализу: агент читает файл и правит Module.bsl."""
    if not analysis_path or not os.path.isfile(analysis_path):
        return False, "Файл анализа не найден"
    bsl_file = "xml/CommonModules/ИИА_DSL/Ext/Module.bsl"
    prompt = f"""ЗАДАЧА: Прочитай анализ в файле {analysis_path} и исправь баги в {bsl_file} согласно рекомендациям.

НЕ спрашивай — сразу открой {bsl_file}, внеси изменения, сохрани.
Не коммить и не пушить."""
    if comment:
        prompt += f"\nКомментарий пользователя (учесть): {comment}"
    agent_path, kind = _find_agent_cmd(prefer_cursor=False)
    if not agent_path:
        return False, "Cursor Agent CLI не найден. Запустите: python check_cursor_cli.py"
    base = ["--trust", "-f", "--workspace", _root, "-p", prompt,
            "--model", "Composer 1.5", "--mode", "agent", "--sandbox", "disabled"]
    cmd = [agent_path] + base if kind == "agent" else [agent_path, "agent"] + base
    try:
        result = subprocess.run(cmd, cwd=_root, timeout=CURSOR_APPLY_TIMEOUT,
                               text=True, encoding="utf-8", errors="replace")
        if result.returncode == 0:
            _print_git_status()
        return result.returncode == 0, ""
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

        if not getattr(args, "skip_update", False):
            print("Обновление расширения и БД...")
            if not run_update_1c():
                print("Ошибка обновления БД. Запустите: python update_1c.py --skip-run-client", file=sys.stderr)
                return 1
        else:
            print("--skip-update: пропуск обновления БД")

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
        analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Анализ сохранён: {analysis_path}")

        if not output.strip():
            print("Анализ пуст.")
            send_telegram_notification(
                f"<b>Анализ пуст</b>\n\nRun: {run_id}\nПровалы: {', '.join(failed)}\n"
                f"Проверьте логи: {log_dir}"
            )
            return 1

        # Отправка сырого анализа в Telegram (если не --no-approval)
        if not getattr(args, "no_approval", False):
            send_raw_analysis(
                run_id=run_id,
                raw_output=output,
                total_tokens=total_tokens,
                cost_rub=round(total_cost_rub, 2),
                failed_ids=failed,
            )
            print("Ожидание одобрения в Telegram (ответьте или нажмите кнопку)...")
            action, approved, comment = wait_for_approval(timeout_sec=APPROVAL_TIMEOUT)
            if action == "reject":
                send_telegram_notification("Ответ получен: <b>отклонено</b>.")
                print("Правки отклонены.")
                return 1
            if action == "timeout":
                send_telegram_notification("Таймаут ожидания одобрения.")
                print("Таймаут ожидания одобрения.")
                return 1
            if comment:
                print(f"Комментарий: {comment}")
            send_telegram_notification("<b>Ответ получен</b>: одобрено. Применение правок...")
        else:
            comment = ""
            print("--no-approval: применяем все без ожидания в Telegram")

        # Применение (сырой анализ → агент читает файл и правит)
        print("Применение правок через Cursor CLI...")
        ok, msg = run_cursor_apply_from_analysis(analysis_path, comment)
        if not ok:
            print(f"Ошибка применения: {msg}", file=sys.stderr)
            send_telegram_notification(f"<b>Ошибка применения правок</b>\n\n<pre>{msg[:500]}</pre>")
            return 1

        # Результат изменений в Telegram
        git_status = _get_git_status()
        tg_msg = "<b>Правки применены</b>\n\n"
        if git_status:
            tg_msg += f"Изменённые файлы:\n<pre>{git_status[:1500]}</pre>\n\n"
        send_telegram_notification(tg_msg)

        # Обновление БД и запуск тестов после правок
        if not getattr(args, "skip_update", False):
            print("Обновление расширения и БД...")
            run_update_1c()
        print("Запуск тестов после правок...")
        rc, new_run_id, new_report_path = run_tests(examples_arg)
        if new_report_path:
            new_report = load_report(new_report_path)
            new_failed, new_passed = get_failed_and_passed(new_report)
            passed_ids.update(new_passed)
            run_tokens = new_report.get("total_tokens", 0)
            run_cost = new_report.get("cost_rub", 0)
            total_tokens += run_tokens
            total_cost_rub += run_cost
            state["passed_ids"] = sorted(passed_ids)
            state["total_tokens"] = total_tokens
            state["total_cost_rub"] = round(total_cost_rub, 2)
            state["last_run_id"] = new_run_id
            save_cycle_state(state)
            passed_count = len(new_report.get("results", [])) - len(new_failed)
            total_count = len(new_report.get("results", []))
            all_ok = not new_failed
            send_telegram_notification(
                f"<b>Результат тестов после правок</b>\n\n"
                f"Пройдено: {passed_count}/{total_count}\n"
                f"Токены: {run_tokens:,} | Стоимость: ~{run_cost} ₽\n"
                f"Каталог: <code>{new_report_path}</code>\n"
                f"{'✅ Все пройдены' if all_ok else '❌ Есть провалы: ' + ', '.join(new_failed)}"
            )
            if all_ok:
                send_telegram_notification(
                    f"<b>Все тесты пройдены</b>\n\nТокены за цикл: {total_tokens:,} | Стоимость: ~{total_cost_rub} ₽"
                )
                print("Все тесты пройдены.")
                return 0
        continue  # Повтор цикла (анализ провалов и т.д.)


def cmd_run_tests_only(args):
    """Только запуск тестов."""
    rc, run_id, report_path = run_tests()
    print(f"Run ID: {run_id}, Report: {report_path}")
    return rc


def _find_report_for_run(run_id: str):
    """Находит (report_path, log_dir) для run_id или (None, None)."""
    report_path = os.path.join(_log_dir(), run_id, "report.json")
    if os.path.isfile(report_path):
        return report_path, os.path.dirname(report_path)
    for p in Path(_log_dir()).glob(f"*{run_id}*/report.json"):
        return str(p), str(p.parent)
    for p in Path(_log_dir()).glob(f"{run_id}/report.json"):
        return str(p), str(p.parent)
    return None, None


def cmd_run_from(args):
    """Полный цикл от существующего прогона: анализ (если нужно) → TG → правки → тесты."""
    run_id = args.run_from
    report_path, log_dir = _find_report_for_run(run_id)
    if not report_path:
        print(f"Report не найден для {run_id}. Укажите run_id, например examples_20260227_045200", file=sys.stderr)
        return 1
    run_id = os.path.basename(log_dir)
    report = load_report(report_path)
    failed, passed_list = get_failed_and_passed(report)
    state = load_cycle_state()
    passed_ids = set(state.get("passed_ids", []))
    passed_ids.update(passed_list)
    total_tokens = state.get("total_tokens", 0) + report.get("total_tokens", 0)
    total_cost_rub = state.get("total_cost_rub", 0) + report.get("cost_rub", 0)
    all_ids = {e["id"] for e in README_EXAMPLES}
    state["passed_ids"] = sorted(passed_ids)
    state["total_tokens"] = total_tokens
    state["total_cost_rub"] = round(total_cost_rub, 2)
    state["last_run_id"] = run_id
    save_cycle_state(state)

    if not failed:
        print("Все тесты в этом прогоне пройдены. Запуск тестов для проверки...")
        rc, new_run_id, new_report_path = run_tests()
        if new_report_path:
            new_report = load_report(new_report_path)
            nf, _ = get_failed_and_passed(new_report)
            if not nf:
                print("Все тесты пройдены.")
                return 0
        print("Есть провалы. Запустите --run-from", new_run_id or run_id)
        return 0

    analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
    if not os.path.isfile(analysis_path):
        print("Анализ через Cursor CLI...")
        output = run_cursor_analyze(run_id, report_path, log_dir)
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Анализ сохранён: {analysis_path}")
    else:
        with open(analysis_path, "r", encoding="utf-8") as f:
            output = f.read()
        print(f"Используем существующий анализ: {analysis_path}")

    if not output.strip():
        print("Анализ пуст.", file=sys.stderr)
        return 1

    if not getattr(args, "no_approval", False):
        send_raw_analysis(run_id=run_id, raw_output=output, total_tokens=total_tokens, cost_rub=round(total_cost_rub, 2), failed_ids=failed)
        print("Ожидание одобрения в Telegram...")
        action, approved, comment = wait_for_approval(timeout_sec=APPROVAL_TIMEOUT)
        if action == "reject":
            send_telegram_notification("Ответ получен: <b>отклонено</b>.")
            print("Правки отклонены.")
            return 1
        if action == "timeout":
            send_telegram_notification("Таймаут ожидания одобрения.")
            print("Таймаут ожидания.")
            return 1
        if comment:
            print(f"Комментарий: {comment}")
        send_telegram_notification("<b>Ответ получен</b>: одобрено. Применение правок...")
    else:
        comment = ""
        print("--no-approval: применяем все без ожидания в Telegram")

    print("Применение правок...")
    ok, msg = run_cursor_apply_from_analysis(analysis_path, comment)
    if not ok:
        print(f"Ошибка: {msg}", file=sys.stderr)
        return 1

    git_status = _get_git_status()
    tg_msg = "<b>Правки применены</b>\n\n"
    if git_status:
        tg_msg += f"Изменённые файлы:\n<pre>{git_status[:1500]}</pre>\n\n"
    send_telegram_notification(tg_msg)

    if not getattr(args, "skip_update", False):
        print("Обновление расширения и БД...")
        run_update_1c()
    print("Запуск тестов после правок...")
    rc, new_run_id, new_report_path = run_tests()
    if new_report_path:
        new_report = load_report(new_report_path)
        nf, np = get_failed_and_passed(new_report)
        passed_count = len(np)
        total_count = len(new_report.get("results", []))
        send_telegram_notification(
            f"<b>Результат тестов после правок</b>\n\n"
            f"Пройдено: {passed_count}/{total_count}\n"
            f"Токены: {new_report.get('total_tokens', 0):,} | Стоимость: ~{new_report.get('cost_rub', 0)} ₽\n"
            f"Каталог: <code>{new_report_path}</code>\n"
            f"{'✅ Все пройдены' if not nf else '❌ Есть провалы: ' + ', '.join(nf)}"
        )
        if not nf:
            print("Все тесты пройдены.")
            return 0
    print("Есть провалы. Запустите --run-from", new_run_id or run_id)
    return 0


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
    analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Анализ сохранён: {analysis_path}")
    return 0


def cmd_apply(args):
    """Применить правки по анализу (сырой анализ → агент правит Module.bsl)."""
    run_id = args.apply
    analysis_path = None
    report_path, log_dir = _find_report_for_run(run_id)
    if log_dir:
        for p in Path(log_dir).glob("analysis_*.md"):
            analysis_path = str(p)
            break
    if not analysis_path or not os.path.isfile(analysis_path):
        for p in Path(_log_dir()).glob(f"*{run_id}*/analysis_*.md"):
            analysis_path = str(p)
            break
        else:
            print(f"Анализ не найден для {run_id}. Сначала выполните --analyze.", file=sys.stderr)
            return 1
    comment = (args.approve or "").strip()  # --approve используется как комментарий
    ok, msg = run_cursor_apply_from_analysis(analysis_path, comment)
    if not ok:
        print(f"Ошибка: {msg}", file=sys.stderr)
        return 1

    git_status = _get_git_status()
    tg_msg = "<b>Правки применены</b>\n\n"
    if git_status:
        tg_msg += f"Изменённые файлы:\n<pre>{git_status[:1500]}</pre>\n\n"
    send_telegram_notification(tg_msg)

    if not getattr(args, "skip_update", False):
        print("Обновление расширения и БД...")
        run_update_1c()
    print("Запуск тестов после правок...")
    rc, new_run_id, new_report_path = run_tests()
    if new_report_path:
        new_report = load_report(new_report_path)
        nf, np = get_failed_and_passed(new_report)
        passed_count = len(np)
        total_count = len(new_report.get("results", []))
        send_telegram_notification(
            f"<b>Результат тестов после правок</b>\n\n"
            f"Пройдено: {passed_count}/{total_count}\n"
            f"Токены: {new_report.get('total_tokens', 0):,} | Стоимость: ~{new_report.get('cost_rub', 0)} ₽\n"
            f"Каталог: <code>{new_report_path}</code>\n"
            f"{'✅ Все пройдены' if not nf else '❌ Есть провалы: ' + ', '.join(nf)}"
        )
        return 0 if not nf else 1
    return 1


def main():
    setup_console_encoding()
    import argparse
    parser = argparse.ArgumentParser(description="CLI цикл: тест - анализ - согласование - правки")
    parser.add_argument("--run", "-r", action="store_true", help="Полный цикл (тесты - анализ - TG - правки - повтор)")
    parser.add_argument("--run-from", metavar="RUN_ID", help="Цикл от существующего прогона (анализ - TG - правки - тесты)")
    parser.add_argument("--run-tests-only", action="store_true", help="Только запуск тестов")
    parser.add_argument("--analyze", metavar="RUN_ID", help="Анализ готового прогона (например examples_20250227_143000)")
    parser.add_argument("--apply", metavar="RUN_ID", help="Применить правки по анализу")
    parser.add_argument("--approve", help="Комментарий для агента (с --apply)")
    parser.add_argument("--no-approval", action="store_true", help="Без ожидания в Telegram — сразу применить все")
    parser.add_argument("--skip-update", action="store_true", help="Пропустить обновление БД перед тестами")
    args = parser.parse_args()
    if args.run:
        return cmd_run(args)
    if args.run_from:
        return cmd_run_from(args)
    if args.run_tests_only:
        return cmd_run_tests_only(args)
    if args.analyze:
        return cmd_analyze(args)
    if args.apply:
        return cmd_apply(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
