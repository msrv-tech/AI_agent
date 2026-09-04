# -*- coding: utf-8 -*-
"""Browser-based quality gate for 1C:Fresh cloud (without COM/HTTP bridge).

Runs the same README examples as automation/com_1c/test_examples.py through the
published web-client: OpenID login, agent form, prompt submission, UI log capture,
heuristic scoring and scenario rules.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import statistics
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT, AUTOMATION_ROOT / "com_1c"):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from automation.ui.web_agent_modes_e2e import send_prompt, switch_mode
from automation.ui.web_agent_skill_e2e import click_label, close_font_dialog
from automation.ui.web_document_recognition_e2e import wait_for_agent_state
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding
from test_examples import (  # noqa: E402
    EXAMPLE_GROUPS,
    QUALITY_GATE_MIN_AVG_SCORE,
    QUALITY_GATE_MIN_SINGLE_SCORE,
    README_EXAMPLES,
    analyze_log,
    calculate_heuristic_score,
    categorize_failure,
    evaluate_scenario_rules,
)

DEFAULT_WEB_URL = "https://1cfresh.com/a/sbm/2226502/ru_RU/"


def resolve_examples(args: argparse.Namespace) -> list[dict]:
    if args.example:
        items = [item for item in README_EXAMPLES if item["id"] == args.example]
        if not items:
            raise RuntimeError(f"Пример '{args.example}' не найден.")
        return items
    if args.examples:
        ids = {part.strip() for part in args.examples.split(",") if part.strip()}
        items = [item for item in README_EXAMPLES if item["id"] in ids]
        if not items:
            raise RuntimeError(f"Примеры '{args.examples}' не найдены.")
        return items
    if args.examples_group:
        groups = [part.strip() for part in args.examples_group.split(",") if part.strip()]
        unknown = [group for group in groups if group not in EXAMPLE_GROUPS]
        if unknown:
            raise RuntimeError(
                f"Неизвестные группы: {', '.join(unknown)}. Доступно: {', '.join(sorted(EXAMPLE_GROUPS))}"
            )
        selected_ids: set[str] = set()
        for group in groups:
            selected_ids.update(EXAMPLE_GROUPS[group])
        items = [item for item in README_EXAMPLES if item["id"] in selected_ids]
        if not items:
            raise RuntimeError(f"Группа(ы) '{args.examples_group}' не содержит сценариев.")
        return items
    return list(README_EXAMPLES)


def dialog_mode_name(dialog_type: str) -> str:
    mapping = {"Agent": "Агент", "Агент": "Агент", "Запрос1С": "Запрос1С", "Zapros1S": "Запрос1С"}
    return mapping.get(dialog_type, "Запрос1С")


def read_agent_log_text(test: BrowserQuery1CTest) -> str:
    script = r"""
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 40 && r.height > 15 && r.x > -1000 && r.y > -1000
      && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const areas = Array.from(document.querySelectorAll('textarea')).filter(visible)
    .map((el) => el.value || '')
    .filter(Boolean);
  const body = document.body ? document.body.innerText || '' : '';
  return areas.join('\n') + '\n' + body;
})()
"""
    return test._evaluate(script)


def extract_usage_tokens(log_text: str) -> int:
    matches = re.findall(r"(?:UsageTokens|usage_tokens|использовано\s+токен(?:ов)?)\D{0,12}(\d+)", log_text, re.I)
    if not matches:
        return 0
    return max(int(value) for value in matches)


def ui_success_from_state(state: dict, analysis: dict) -> bool:
    body_text = str(state.get("bodyText") or "")
    if state.get("state") == "error":
        return False
    if "Задача выполнена успешно" in body_text:
        return True
    if analysis.get("summary_present") and analysis.get("summary_confirmed"):
        return True
    if analysis.get("approval_pending"):
        return True
    return state.get("state") == "success"


def open_agent_form(test: BrowserQuery1CTest, web_url: str, timeout_sec: int) -> None:
    encoded_command = "CommonCommand.%D0%98%D0%98%D0%90_%D0%90%D0%B3%D0%B5%D0%BD%D1%82"
    target_url = web_url.rstrip("/") + f"/#e1cib/command/{encoded_command}"
    test._session_call("Page.navigate", {"url": target_url})
    if not test._wait_for_agent_form(timeout_sec):
        raise RuntimeError("Форма ИИ Агент не открылась в облачном web-client.")


def build_report(results: list[dict], run_log_dir: Path, run_prefix: str) -> dict:
    passed_count = sum(1 for item in results if item.get("passed"))
    scores = [int(item.get("score", 1)) for item in results] or [1]
    avg_score = round(sum(scores) / len(scores), 2)
    min_score = min(scores)
    all_success = all(item.get("passed") for item in results)
    quality_gate_passed = (
        all_success
        and avg_score >= QUALITY_GATE_MIN_AVG_SCORE
        and min_score >= QUALITY_GATE_MIN_SINGLE_SCORE
    )
    return {
        "timestamp": run_prefix.replace("examples_", ""),
        "run_id": run_prefix,
        "log_dir": str(run_log_dir),
        "total": len(results),
        "passed_count": passed_count,
        "success_count": passed_count,
        "all_success": all_success,
        "avg_score": avg_score,
        "median_score": round(statistics.median(scores), 2),
        "min_score": min_score,
        "max_score": max(scores),
        "quality_gate_passed": quality_gate_passed,
        "quality_gate_thresholds": {
            "avg_score_min": QUALITY_GATE_MIN_AVG_SCORE,
            "single_score_min": QUALITY_GATE_MIN_SINGLE_SCORE,
        },
        "quality_warning": all_success and not quality_gate_passed,
        "transport": "web",
        "results": results,
    }


def run(args: argparse.Namespace) -> dict:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_prefix = f"examples_{timestamp}"
    log_dir = Path(args.log_dir)
    run_log_dir = log_dir / run_prefix
    run_log_dir.mkdir(parents=True, exist_ok=True)

    examples = resolve_examples(args)
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    config = WebUiConfig(
        web_url=args.web_url,
        chrome_exe=args.chrome_exe,
        base_path="",
        user=args.user,
        password=args.password,
        query_text="",
        query_params_json="",
        expected_text="",
        timeout_sec=args.timeout_sec,
        log_file=str(artifact_dir / "web_com_gate.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    logger = Logger(config.log_file)
    test = BrowserQuery1CTest(config, logger)
    results: list[dict] = []

    try:
        test._launch_browser()
        test._open_initial_target()
        test._login()
        close_font_dialog()
        open_agent_form(test, args.web_url, args.timeout_sec)

        for example in examples:
            print(f"\n--- {example['id']}: {example['description']} ---")
            auto_confirm = bool(args.auto_confirm or example.get("auto_confirm") or example.get("type") == "Запрос1С")
            mode = dialog_mode_name(example.get("type", "Запрос1С"))
            try:
                switch_mode(test, mode)
                send_prompt(test, example["text"])
                state = wait_for_agent_state(test, args.agent_wait_sec, auto_confirm=auto_confirm)
                log_text = read_agent_log_text(test)
                if state.get("bodyText") and state["bodyText"] not in log_text:
                    log_text = str(state["bodyText"]) + "\n" + log_text
                success = ui_success_from_state(state, analyze_log(log_text))
                usage_tokens = extract_usage_tokens(log_text)
                analysis = analyze_log(log_text)
                scenario_eval = evaluate_scenario_rules(example, success, analysis, usage_tokens)
                heuristic = calculate_heuristic_score(example, success, analysis, usage_tokens, scenario_eval)
                allow_pending = bool(scenario_eval.get("rule", {}).get("allow_pending_approval"))
                approval_passed = bool(allow_pending and analysis.get("approval_pending"))
                base_passed = approval_passed or (
                    success and analysis["summary_present"] and analysis["summary_confirmed"]
                )
                passed = base_passed and bool(scenario_eval.get("passed"))
                item = {
                    "id": example["id"],
                    "text": example["text"],
                    "type": example["type"],
                    "success": success,
                    "passed": passed,
                    "base_passed": base_passed,
                    "scenario_passed": bool(scenario_eval.get("passed")),
                    "usage_tokens": usage_tokens,
                    "dialog_ref": "",
                    "has_error": analysis["has_error"],
                    "error_count": len(analysis["error_lines"]),
                    "summary_present": analysis["summary_present"],
                    "summary_confirmed": analysis["summary_confirmed"],
                    "approval_pending": bool(analysis.get("approval_pending")),
                    "dsl_actions": analysis["dsl_actions_found"],
                    "recovery_attempts": analysis.get("recovery_attempts", 0),
                    "runquery_zero_rows": analysis.get("runquery_zero_rows", False),
                    "scenario_violations": scenario_eval.get("violations", []),
                    "score": int(heuristic["score"]),
                    "score_mode": "heuristic",
                    "score_breakdown": heuristic.get("breakdown", {}),
                    "score_reason": "Оценка по эвристике (web)",
                    "ui_state": state.get("state"),
                }
                item["failure_categories"] = categorize_failure(item)
                log_path = run_log_dir / f"{example['id']}.txt"
                log_path.write_text(
                    f"[{example['id']}] {example['text']}\n"
                    f"Тип: {example['type']} | Успех: {success} | Passed: {passed}\n"
                    f"{'=' * 60}\n"
                    f"{log_text or '(лог пуст)'}\n",
                    encoding="utf-8",
                )
                item["log_file"] = str(log_path)
                print(
                    f"  Результат: {'OK' if passed else 'FAIL'} | Score: {item['score']}/100 | state={state.get('state')}"
                )
            except Exception as exc:
                log_path = run_log_dir / f"{example['id']}.txt"
                log_path.write_text(f"[{example['id']}] ИСКЛЮЧЕНИЕ: {exc}\n", encoding="utf-8")
                item = {
                    "id": example["id"],
                    "success": False,
                    "passed": False,
                    "error": str(exc),
                    "score": 1,
                    "log_file": str(log_path),
                    "failure_categories": ["runtime_exception"],
                }
                print(f"  ОШИБКА: {exc}")
            results.append(item)
    finally:
        test._close()

    report = build_report(results, run_log_dir, run_prefix)
    report_file = run_log_dir / "report.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    report["report_file"] = str(report_file)
    return report


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser quality gate for 1C:Fresh cloud")
    parser.add_argument("--web-url", default=os.getenv("FRESH_CLOUD_WEB_URL", DEFAULT_WEB_URL))
    parser.add_argument(
        "--chrome-exe",
        default=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    parser.add_argument("--user", default=os.getenv("FRESH_CLOUD_USER", ""))
    parser.add_argument("--password", default=os.getenv("FRESH_CLOUD_PASSWORD", ""))
    parser.add_argument("--examples-group", default="extended")
    parser.add_argument("--example")
    parser.add_argument("--examples")
    parser.add_argument("--score-mode", default="heuristic", choices=["heuristic"])
    parser.add_argument("--log-dir", default=str(REPO_ROOT / "automation" / "logs"))
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "web_com_gate"))
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument("--agent-wait-sec", type=int, default=180)
    parser.add_argument("--auto-confirm", action="store_true")
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    if not args.user:
        print("Ошибка: задайте --user или FRESH_CLOUD_USER для входа в 1С:Фреш.", file=sys.stderr)
        return 2
    report = run(args)
    print(
        f"\nQuality gate: {'PASS' if report['quality_gate_passed'] else 'FAIL'} "
        f"({report['passed_count']}/{report['total']}, avg={report['avg_score']}, min={report['min_score']})"
    )
    print(f"Report: {report['report_file']}")
    return 0 if report["quality_gate_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
