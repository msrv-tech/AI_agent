# -*- coding: utf-8 -*-
"""
CLI цикл: тест → анализ → согласование в Telegram → правки → повтор.

Запуск (из каталога automation или корня проекта):
    python test_fix_cycle.py --run              # полный цикл (тесты - анализ - TG - правки)
    python test_fix_cycle.py --run-from readme_20260227_045200  # от существующего прогона
    python test_fix_cycle.py --run-tests-only   # только тесты
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
    # Строгий формат PROPOSAL
    pattern = re.compile(
        r"PROPOSAL\s+(\d+)\s*[\r\n]+"
        r"FILE:\s*(.+?)[\r\n]+"
        r"DESCRIPTION:\s*(.+?)[\r\n]+"
        r"PATCH:\s*[\r\n]*<<<<<<[\r\n]+(.*?)>>>>>>\s*[\r\n]*"
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
            file_m = re.search(r"FILE:\s*(.+?)(?:\r?\n|$)", part)
            desc_m = re.search(r"DESCRIPTION:\s*(.+?)(?:\r?\n|$)", part)
            patch_m = re.search(r"<<<<<<\s*\r?\n(.*?)>>>>>>", part, re.DOTALL)
            if file_m:
                proposals.append({
                    "index": i,
                    "file": file_m.group(1).strip(),
                    "description": (desc_m.group(1) if desc_m else "").strip()[:200],
                    "patch": (patch_m.group(1) if patch_m else "").strip(),
                })
    # Fallback: извлечение из блоков ```diff
    if not proposals:
        for m in re.finditer(r"```(?:diff)?\s*\n(.*?)```", text, re.DOTALL):
            patch = m.group(1).strip()
            if patch and ("---" in patch or "+++" in patch or "@@" in patch):
                file_m = re.search(r"(?:---|\+\+\+)\s+[ab]/(.+?)(?:\s|$)", patch)
                path = file_m.group(1).strip() if file_m else "xml/CommonModules/ИИА_DSL/Ext/Module.bsl"
                if not path.startswith("xml/"):
                    path = f"xml/{path}" if not path.startswith("/") else path
                proposals.append({
                    "index": len(proposals) + 1,
                    "file": path,
                    "description": "Извлечено из блока diff",
                    "patch": patch,
                })
    # Fallback: извлечение из markdown-анализа (таблица "Корневые причины", "Баг BSL")
    if not proposals:
        proposals = _parse_proposals_from_analysis(text)
    return proposals


def _parse_proposals_from_analysis(text: str):
    """Извлекает предложения из markdown-анализа (таблица с Баг BSL, рекомендации)."""
    proposals = []
    # Таблица: | # | Проблема | Тесты | Тип | ... | 1 | ... | **Баг BSL** |
    # Ищем строки таблицы с **Баг BSL**
    bsl_file = "xml/CommonModules/ИИА_DSL/Ext/Module.bsl"
    for m in re.finditer(r"\|\s*(\d+)\s*\|\s*([^|]+)\|\s*[^|]+\|\s*\*\*Баг BSL\*\*", text):
        idx, problem = int(m.group(1)), m.group(2).strip()
        problem = re.sub(r"`([^`]+)`", r"\1", problem)[:200]
        if problem and not any(p["description"] == problem for p in proposals):
            proposals.append({
                "index": len(proposals) + 1,
                "file": bsl_file,
                "description": problem,
                "patch": "",
            })
    # Рекомендации: "- В модуле `ИИА_DSL` -- после CreateDocument..."
    if not proposals:
        for m in re.finditer(r"[-*]\s+В модуле\s+`?ИИА_DSL`?\s*[—\-]\s*(.+?)(?:\n|$)", text):
            desc = m.group(1).strip()[:200]
            if desc and len(proposals) < 5:
                proposals.append({
                    "index": len(proposals) + 1,
                    "file": bsl_file,
                    "description": desc,
                    "patch": "",
                })
    return proposals


def _print_git_status():
    """Выводит git status после применения правок."""
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
            print("Изменённые файлы (git status):")
            print(r.stdout.strip())
        elif r.returncode == 0:
            print("(git: изменений нет)")
    except Exception:
        pass


def run_cursor_apply(proposals, approved_indices, proposals_path, comment: str = "", analysis_path: str = ""):
    """Применяет одобренные предложения через Cursor CLI."""
    if not approved_indices:
        approved_indices = list(range(1, len(proposals) + 1))
    selected = [p for p in proposals if p["index"] in approved_indices]
    if not selected:
        return False, "Нет предложений для применения"
    has_patches = all(p.get("patch") for p in selected)
    if has_patches:
        prompt = f"""Примени следующие правки из файла {proposals_path}.
Номера одобренных предложений: {approved_indices}
Не коммить и не пушить — оставь изменения в рабочей директории для ручного просмотра.
"""
    else:
        # Предложения без patch — реализовать по описанию
        file_path = selected[0]["file"]
        tasks = "\n".join(f"{i+1}. {p['description']}" for i, p in enumerate(selected))
        prompt = f"""ЗАДАЧА: Исправь баги в файле {file_path}. НЕ спрашивай — сразу открой файл и внеси изменения.

Исправления (сделай все):
{tasks}

Открой {file_path}, отредактируй, сохрани. Не коммить и не пушить."""
        if analysis_path and os.path.isfile(analysis_path):
            prompt += f"\nКонтекст: {analysis_path}"
    if comment:
        prompt += f"\nКомментарий пользователя (учесть при применении): {comment}"
    # standalone agent корректно принимает --workspace, -p и т.д.; cursor agent передаёт в Electron
    agent_path, kind = _find_agent_cmd(prefer_cursor=False)
    if not agent_path:
        return False, "Cursor Agent CLI не найден. Запустите: python check_cursor_cli.py"
    cfg = os.path.join(_root, ".cursor")
    print(f"Применение через: {'cursor agent' if kind == 'cursor_agent' else 'agent'}")
    if os.path.isfile(os.path.join(cfg, "sandbox.json")):
        print("  .cursor/sandbox.json (type: insecure_none)")
    if os.path.isfile(os.path.join(cfg, "cli.json")):
        print("  .cursor/cli.json (Write xml/**)")
    base = ["--trust", "-f", "--workspace", _root, "-p", prompt,
            "--model", "Composer 1.5", "--mode", "agent", "--sandbox", "disabled"]
    if kind == "agent":
        cmd = [agent_path] + base
    else:
        cmd = [agent_path, "agent"] + base
    try:
        result = subprocess.run(
            cmd,
            cwd=_root,
            timeout=CURSOR_APPLY_TIMEOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        ok = result.returncode == 0
        if ok:
            _print_git_status()
        return ok, ""
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
        analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
        with open(proposals_path, "w", encoding="utf-8") as f:
            json.dump({"proposals": proposals, "raw_output": output[:5000]}, f, ensure_ascii=False, indent=2)
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Анализ сохранён: {analysis_path}")

        if not proposals:
            print("Предложения не получены. Raw output:", output[:500])
            send_telegram_notification(
                f"<b>Анализ не дал предложений</b>\n\n"
                f"Run: {run_id}\nПровалы: {', '.join(failed)}\n"
                f"Анализ сохранён: <code>{analysis_path}</code>\n"
                f"Проверьте логи: {log_dir}"
            )
            return 1

        # Отправка в Telegram (если не --no-approval)
        if not getattr(args, "no_approval", False):
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
                send_telegram_notification("Ответ получен: <b>отклонено</b>.")
                print("Правки отклонены.")
                return 1
            if action == "timeout":
                send_telegram_notification("Таймаут ожидания одобрения.")
                print("Таймаут ожидания одобрения.")
                return 1
            approved_indices = approved if action == "approve_partial" else []
            if action == "approve_all":
                approved_indices = [p["index"] for p in proposals]
            if comment:
                print(f"Комментарий: {comment}")
            send_telegram_notification(
                f"<b>Ответ получен</b>: одобрено {len(approved_indices)} из {len(proposals)}. Применение правок..."
            )
        else:
            approved_indices = [p["index"] for p in proposals]
            comment = ""
            print("--no-approval: применяем все без ожидания в Telegram")

        # Применение
        print("Применение правок через Cursor CLI...")
        ok, msg = run_cursor_apply(proposals, approved_indices, proposals_path, comment, analysis_path)
        if not ok:
            print(f"Ошибка применения: {msg}", file=sys.stderr)
            send_telegram_notification(f"<b>Ошибка применения правок</b>\n\n<pre>{msg[:500]}</pre>")
            return 1
        print("Правки применены (не запушены). Запуск тестов отключён — проверьте git status.")
        return 0


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
        print(f"Report не найден для {run_id}. Укажите run_id, например readme_20260227_045200", file=sys.stderr)
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

    proposals_path = os.path.join(log_dir, f"proposals_{run_id}.json")
    analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
    proposals = []
    if os.path.isfile(proposals_path):
        with open(proposals_path, "r", encoding="utf-8") as f:
            proposals = json.load(f).get("proposals", [])
    if not proposals:
        print("Анализ через Cursor CLI...")
        output = run_cursor_analyze(run_id, report_path, log_dir)
        proposals = parse_proposals(output)
        with open(proposals_path, "w", encoding="utf-8") as f:
            json.dump({"proposals": proposals, "raw_output": output[:5000]}, f, ensure_ascii=False, indent=2)
        with open(analysis_path, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Анализ сохранён: {analysis_path}")
    else:
        print(f"Используем существующие предложения: {proposals_path}")

    if not proposals:
        print("Предложения не получены.", file=sys.stderr)
        return 1

    if not getattr(args, "no_approval", False):
        send_proposals(run_id=run_id, proposals=proposals, total_tokens=total_tokens, cost_rub=round(total_cost_rub, 2), failed_ids=failed)
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
        approved_indices = approved if action == "approve_partial" else [p["index"] for p in proposals]
        if comment:
            print(f"Комментарий: {comment}")
        send_telegram_notification(
            f"<b>Ответ получен</b>: одобрено {len(approved_indices)} из {len(proposals)}. Применение правок..."
        )
    else:
        approved_indices = [p["index"] for p in proposals]
        comment = ""
        print("--no-approval: применяем все без ожидания в Telegram")

    print("Применение правок...")
    ok, msg = run_cursor_apply(proposals, approved_indices, proposals_path, comment, analysis_path)
    if not ok:
        print(f"Ошибка: {msg}", file=sys.stderr)
        return 1
    print("Правки применены. Запуск тестов отключён — проверьте git status.")
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
    proposals = parse_proposals(output)
    out_path = os.path.join(log_dir, f"proposals_{run_id}.json")
    analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"proposals": proposals, "raw_output": output[:5000]}, f, ensure_ascii=False, indent=2)
    with open(analysis_path, "w", encoding="utf-8") as f:
        f.write(output)
    print(f"Предложений: {len(proposals)}, proposals: {out_path}, анализ: {analysis_path}")
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
    log_dir = os.path.dirname(proposals_path)
    analysis_path = os.path.join(log_dir, f"analysis_{run_id}.md")
    ok, msg = run_cursor_apply(proposals, approved, proposals_path, analysis_path=analysis_path)
    if not ok:
        print(f"Ошибка: {msg}", file=sys.stderr)
        return 1
    print("Правки применены. Запуск тестов отключён — проверьте git status.")
    return 0


def main():
    setup_console_encoding()
    import argparse
    parser = argparse.ArgumentParser(description="CLI цикл: тест - анализ - согласование - правки")
    parser.add_argument("--run", "-r", action="store_true", help="Полный цикл (тесты - анализ - TG - правки - повтор)")
    parser.add_argument("--run-from", metavar="RUN_ID", help="Цикл от существующего прогона (анализ - TG - правки - тесты)")
    parser.add_argument("--run-tests-only", action="store_true", help="Только запуск тестов")
    parser.add_argument("--analyze", metavar="RUN_ID", help="Анализ готового прогона (например readme_20250227_143000)")
    parser.add_argument("--apply", metavar="RUN_ID", help="Применить одобренные предложения")
    parser.add_argument("--approve", help="Номера предложений через запятую: 1,3 (с --apply)")
    parser.add_argument("--no-approval", action="store_true", help="Без ожидания в Telegram — сразу применить все")
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
        if not args.approve:
            print("С --apply укажите --approve 1,2,3", file=sys.stderr)
            return 1
        return cmd_apply(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
