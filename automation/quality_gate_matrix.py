# -*- coding: utf-8 -*-
"""Release quality gate runner for the 1C AI Agent.

Runs the reusable HTTP-bridge scenarios against one or more configurations and,
optionally, browser E2E tests for skills, write flow, negative UI and
document recognition. The script intentionally orchestrates existing tests
instead of duplicating their assertions.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.bridge.config import DEFAULT_BP_BRIDGE_URL, DEFAULT_UNF_BRIDGE_URL
DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_UNF_BRIDGE_URL
DEFAULT_CLOUD_WEB_URL = os.getenv("FRESH_CLOUD_WEB_URL", "https://1cfresh.com/a/sbm/2226502/ru_RU/")
DEFAULT_SUPPLIER_INVOICE = REPO_ROOT / "temp" / "Счет на оплату № 6 от 26 августа 2025 г.pdf"


DOC_RECOGNITION_CASES = {
    "supplier_invoice": {
        "prompt": "распознай счет поставщика по приложенному файлу и подготовь документ в базе",
        "expected_skill": "recognize-supplier-invoice",
        "expected_target": "СчетНаОплатуПоставщика",
    },
    "upd_torg12": {
        "prompt": "распознай УПД или ТОРГ-12 по приложенному файлу и подготовь документ поступления",
        "expected_skill": "recognize-upd-torg12",
        "expected_target": "ПоступлениеТоваровУслуг",
    },
    "service_act": {
        "prompt": "распознай акт услуг по приложенному файлу и подготовь документ поступления услуг",
        "expected_skill": "recognize-service-act",
        "expected_target": "ПоступлениеТоваровУслуг",
    },
    "vat_invoice": {
        "prompt": "распознай счет-фактуру по приложенному файлу и подготовь документ в базе",
        "expected_skill": "recognize-invoice-factura",
        "expected_target": "СчетФактураПолученный",
    },
}


def run_command(cmd: list[str], timeout_sec: int, cwd: Path = REPO_ROOT) -> dict:
    started = time.time()
    completed = subprocess.run(
        cmd,
        cwd=str(cwd),
        text=True,
        encoding="utf-8",
        errors="replace",
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout_sec,
    )
    return {
        "cmd": cmd,
        "returncode": completed.returncode,
        "duration_sec": round(time.time() - started, 2),
        "output": completed.stdout,
        "success": completed.returncode == 0,
    }


def read_json_if_exists(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return {"json_read_error": str(exc), "path": str(path)}


def latest_report(log_dir: Path) -> dict:
    reports = sorted(log_dir.glob("examples_*/report.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not reports:
        return {}
    report = read_json_if_exists(reports[0])
    report["report_file"] = str(reports[0])
    return report


def run_bridge_gate(name: str, bridge_url: str, user: str, group: str, score_mode: str, artifact_dir: Path, timeout_sec: int) -> dict:
    log_dir = artifact_dir / "bridge" / name
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "automation/bridge/test_examples.py",
        "--bridge-url",
        bridge_url,
        "--user",
        user,
        "--examples-group",
        group,
        "--score-mode",
        score_mode,
        "--log-dir",
        str(log_dir),
    ]
    result = run_command(cmd, timeout_sec)
    result["name"] = name
    result["kind"] = "bridge_examples"
    result["report"] = latest_report(log_dir)
    if result["success"] and result["report"]:
        result["success"] = bool(result["report"].get("quality_gate_passed"))
    return result


def run_ui_script(script: str, args: list[str], artifact_dir: Path, timeout_sec: int) -> dict:
    cmd = [sys.executable, script, "--artifact-dir", str(artifact_dir), *args]
    result = run_command(cmd, timeout_sec)
    result["kind"] = "ui_e2e"
    result["name"] = Path(script).stem
    result_json = artifact_dir / (Path(script).stem + "_result.json")
    if not result_json.exists():
        result_json = artifact_dir / {
            "web_agent_skill_write_e2e.py": "web_agent_skill_write_e2e_result.json",
            "web_agent_skill_approval_e2e.py": "web_agent_skill_approval_e2e_result.json",
            "web_skills_lifecycle_e2e.py": "web_skills_lifecycle_e2e_result.json",
            "web_skills_negative_ui.py": "web_skills_negative_ui_result.json",
            "web_document_recognition_e2e.py": "web_document_recognition_e2e_result.json",
        }.get(Path(script).name, "")
    result["report"] = read_json_if_exists(result_json)
    return result


def parse_doc_files(raw: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not raw:
        return result
    for part in raw.split(";"):
        item = part.strip()
        if not item:
            continue
        if "=" not in item:
            result.setdefault("supplier_invoice", item)
            continue
        key, value = item.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def recognition_files(raw: str) -> dict[str, str]:
    parsed = parse_doc_files(raw)
    if parsed:
        return parsed
    if DEFAULT_SUPPLIER_INVOICE.is_file():
        return {"supplier_invoice": str(DEFAULT_SUPPLIER_INVOICE)}
    return {}


def build_ui_jobs(args: argparse.Namespace, artifact_dir: Path) -> list[tuple[str, list[str], Path, int]]:
    browser_common = [
        "--web-url", args.web_url,
        "--user", args.user,
        "--password", args.password,
        "--timeout-sec", str(args.ui_timeout_sec),
    ]
    if args.headed:
        browser_common.append("--headed")
    bridge_common = [
        "--web-url", args.web_url,
        "--bridge-url", args.bridge_url,
        "--user", args.user,
        "--password", args.password,
        "--timeout-sec", str(args.ui_timeout_sec),
    ]
    if args.headed:
        bridge_common.append("--headed")
    bridge_only_common = [
        "--bridge-url", args.bridge_url,
        "--user", args.user,
        "--timeout-sec", str(args.ui_timeout_sec),
    ]

    jobs: list[tuple[str, list[str], Path, int]] = []
    if args.include_skill_write:
        jobs.append((
            "automation/ui/web_agent_skill_write_e2e.py",
            bridge_common[:],
            artifact_dir / "ui" / "skill_write",
            args.ui_timeout_sec + 120,
        ))
    if args.include_skill_lifecycle:
        jobs.append((
            "automation/ui/web_skills_lifecycle_e2e.py",
            bridge_common[:],
            artifact_dir / "ui" / "skills_lifecycle",
            args.ui_timeout_sec + 120,
        ))
    if args.include_negative_ui:
        jobs.append((
            "automation/ui/web_skills_negative_ui.py",
            browser_common[:],
            artifact_dir / "ui" / "skills_negative",
            args.ui_timeout_sec + 120,
        ))
    if args.include_result_table_link:
        result_link_args = browser_common[:] + ["--agent-wait-sec", str(args.web_agent_wait_sec)]
        jobs.append((
            "automation/ui/web_result_table_link_e2e.py",
            result_link_args,
            artifact_dir / "ui" / "result_table_link",
            args.web_agent_wait_sec + args.ui_timeout_sec + 90,
        ))
    if args.include_approval:
        jobs.append((
            "automation/ui/web_agent_skill_approval_e2e.py",
            bridge_only_common[:],
            artifact_dir / "ui" / "approval",
            args.ui_timeout_sec + 180,
        ))

    doc_files = parse_doc_files(args.document_files)
    if args.include_document_recognition:
        for case_id, case in DOC_RECOGNITION_CASES.items():
            case_args = bridge_common[:] + [
                "--prompt", case["prompt"],
                "--expected-skill", case["expected_skill"],
                "--expected-target", case["expected_target"],
            ]
            image_path = doc_files.get(case_id) or doc_files.get("all") or ""
            if image_path:
                case_args += ["--image-path", image_path]
            if args.require_document_created:
                case_args.append("--require-created")
            if args.require_visible_created_links:
                case_args.append("--require-visible-created-links")
            if args.auto_confirm:
                case_args.append("--auto-confirm")
            jobs.append((
                "automation/ui/web_document_recognition_e2e.py",
                case_args,
                artifact_dir / "ui" / "document_recognition" / case_id,
                args.ui_timeout_sec + 180,
            ))
    return jobs


def run_web_quality_gate(name: str, web_url: str, user: str, password: str, group: str, artifact_dir: Path, timeout_sec: int, agent_wait_sec: int, auto_confirm: bool, headed: bool) -> dict:
    log_dir = artifact_dir / "web" / name
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "automation/ui/web_quality_gate.py",
        "--web-url",
        web_url,
        "--user",
        user,
        "--password",
        password,
        "--examples-group",
        group,
        "--log-dir",
        str(log_dir),
        "--artifact-dir",
        str(log_dir),
        "--timeout-sec",
        str(max(90, timeout_sec // 10)),
        "--agent-wait-sec",
        str(agent_wait_sec),
    ]
    if auto_confirm:
        cmd.append("--auto-confirm")
    if headed:
        cmd.append("--headed")
    per_example_timeout = max(agent_wait_sec + 120, 240)
    total_timeout = max(timeout_sec, per_example_timeout * 16)
    result = run_command(cmd, total_timeout)
    result["name"] = name
    result["kind"] = "web_examples"
    result["report"] = latest_report(log_dir)
    if result["success"] and result["report"]:
        result["success"] = bool(result["report"].get("quality_gate_passed"))
    return result


def agent_api_url_from_web(web_url: str) -> str:
    base = (web_url or "").rstrip("/")
    for suffix in ("/ru_RU", "/ru", "/en_US"):
        if base.endswith(suffix):
            base = base[: -len(suffix)]
            break
    return base + "/hs/iia-agent"


def run_agent_api_gate(name: str, api_url: str, user: str, password: str, group: str, score_mode: str, artifact_dir: Path, timeout_sec: int, auto_confirm: bool, wait_timeout_sec: int) -> dict:
    log_dir = artifact_dir / "agent_api" / name
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "automation/bridge/test_examples.py",
        "--agent-api-url",
        api_url,
        "--user",
        user,
        "--password",
        password,
        "--examples-group",
        group,
        "--score-mode",
        score_mode,
        "--log-dir",
        str(log_dir),
        "--wait-timeout-sec",
        str(wait_timeout_sec),
    ]
    if auto_confirm:
        cmd.append("--auto-confirm")
    result = run_command(cmd, timeout_sec)
    result["cmd"] = [part if part != password else "***" for part in cmd]
    result["name"] = name
    result["kind"] = "agent_api_examples"
    result["report"] = latest_report(log_dir)
    if result["success"] and result["report"]:
        result["success"] = bool(result["report"].get("quality_gate_passed"))
    return result


def run_agent_api_recognition(
    api_url: str,
    user: str,
    password: str,
    document_files: str,
    artifact_dir: Path,
    wait_timeout_sec: int,
    auto_confirm: bool,
    require_created: bool,
) -> list[dict]:
    from automation.ops.iia_agent_client import UNF_RECOGNITION_CASES, AgentApiClient, AgentApiError

    doc_files = recognition_files(document_files)
    out_dir = artifact_dir / "agent_api" / "document_recognition"
    out_dir.mkdir(parents=True, exist_ok=True)
    if not doc_files:
        return [{
            "name": "cloud_api_document_recognition",
            "kind": "agent_api_document_recognition",
            "success": False,
            "returncode": 2,
            "error": "Файл счёта не найден: " + str(DEFAULT_SUPPLIER_INVOICE) + ". Передайте --document-files. Синтетический файл не создаётся.",
        }]

    selected: list[tuple[str, dict, str]] = []
    shared = doc_files.get("all") or ""
    if shared:
        selected = [(case_id, case, shared) for case_id, case in UNF_RECOGNITION_CASES.items()]
    else:
        unknown = [key for key in doc_files if key not in UNF_RECOGNITION_CASES]
        if unknown:
            return [{
                "name": "cloud_api_document_recognition",
                "kind": "agent_api_document_recognition",
                "success": False,
                "returncode": 2,
                "error": "Неизвестные ключи --document-files: " + ", ".join(unknown),
            }]
        selected = [(case_id, UNF_RECOGNITION_CASES[case_id], path) for case_id, path in doc_files.items()]

    client = AgentApiClient(api_url, user, password)
    results: list[dict] = []
    for case_id, case, file_path in selected:
        name = "cloud_api_recognition_" + case_id
        if not Path(file_path).is_file():
            results.append({
                "name": name,
                "kind": "agent_api_document_recognition",
                "success": False,
                "returncode": 2,
                "error": f"Файл для распознавания не найден: {file_path}",
            })
            continue
        try:
            client.preflight()
            payload = client.run_recognition_case(
                case,
                file_path,
                auto_confirm=auto_confirm,
                wait_timeout_sec=wait_timeout_sec,
                require_created=require_created,
            )
        except AgentApiError as exc:
            results.append({
                "name": name,
                "kind": "agent_api_document_recognition",
                "success": False,
                "returncode": 1,
                "error": str(exc),
            })
            continue
        if payload.get("timeout"):
            payload["passed"] = False
            payload.setdefault("checks", {})["timeout"] = False
        log_file = out_dir / (case_id + "_log.txt")
        log_file.write_text(str(payload.pop("log", "")), encoding="utf-8")
        report = {
            "name": name,
            "kind": "agent_api_document_recognition",
            "success": bool(payload.get("passed")),
            "returncode": 0 if payload.get("passed") else 1,
            "log_file": str(log_file),
            "case": payload,
        }
        (out_dir / (case_id + "_report.json")).write_text(
            json.dumps(report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        results.append(report)
    return results


def apply_profile(args: argparse.Namespace) -> None:
    if args.profile == "cloud-api":
        args.skip_bp = True
        args.skip_unf = True
        args.include_ui = False
        args.include_skill_write = False
        args.include_skill_lifecycle = False
        args.include_negative_ui = False
        args.include_result_table_link = False
        args.include_approval = False
        args.include_document_recognition = False
        if not args.agent_api_url:
            web_url = args.cloud_web_url or os.getenv("FRESH_CLOUD_WEB_URL", DEFAULT_CLOUD_WEB_URL)
            args.agent_api_url = agent_api_url_from_web(web_url)
        env_user = os.getenv("FRESH_CLOUD_USER", "")
        env_password = os.getenv("FRESH_CLOUD_PASSWORD", "")
        if args.user == "Администратор" and env_user:
            args.user = env_user
        if not args.password and env_password:
            args.password = env_password
        return
    if args.profile != "cloud-fresh":
        return
    args.skip_bp = True
    args.skip_unf = True
    if args.cloud_web_url:
        args.web_url = args.cloud_web_url
    else:
        args.web_url = DEFAULT_CLOUD_WEB_URL
    env_user = os.getenv("FRESH_CLOUD_USER", "")
    env_password = os.getenv("FRESH_CLOUD_PASSWORD", "")
    if args.user == "Администратор" and env_user:
        args.user = env_user
    if not args.password and env_password:
        args.password = env_password
    if not args.include_negative_ui and not any(
        flag for flag in (
            args.include_ui,
            args.include_skill_write,
            args.include_skill_lifecycle,
            args.include_approval,
            args.include_document_recognition,
            args.include_result_table_link,
        )
    ):
        args.include_negative_ui = True
        args.include_result_table_link = True


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Release quality gate matrix for 1C AI Agent")
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "quality_gate_matrix"))
    parser.add_argument(
        "--profile",
        default="local",
        choices=["local", "cloud-fresh", "cloud-api"],
        help="local: HTTP-bridge gate по BP/UNF; cloud-fresh: browser gate; cloud-api: сценарии через /hs/iia-agent",
    )
    parser.add_argument(
        "--agent-api-url",
        default=os.getenv("IIA_AGENT_API_URL", ""),
        help="Базовый URL /hs/iia-agent. Для cloud-api по умолчанию строится из FRESH_CLOUD_WEB_URL",
    )
    parser.add_argument("--cloud-web-url", default="", help="URL облачного приложения 1С:Фреш")
    parser.add_argument("--group", default="extended", help="test_examples group: smoke|recovery|write|safety|metadata|extended")
    parser.add_argument("--score-mode", default="heuristic", choices=["heuristic", "llm", "hybrid"])
    parser.add_argument("--bp-bridge", default=DEFAULT_BP_BRIDGE_URL)
    parser.add_argument("--unf-bridge", default=DEFAULT_UNF_BRIDGE_URL)
    parser.add_argument("--bp-user", default="Admin")
    parser.add_argument("--unf-user", default="Администратор")
    parser.add_argument("--skip-bp", action="store_true")
    parser.add_argument("--skip-unf", action="store_true")
    parser.add_argument("--gate-timeout-sec", type=int, default=1800)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--web-agent-wait-sec", type=int, default=180)
    parser.add_argument("--ui-timeout-sec", type=int, default=90)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--include-ui", action="store_true", help="Enable all default UI/E2E suites")
    parser.add_argument("--include-skill-write", action="store_true")
    parser.add_argument("--include-skill-lifecycle", action="store_true")
    parser.add_argument("--include-negative-ui", action="store_true")
    parser.add_argument("--include-result-table-link", action="store_true")
    parser.add_argument("--include-approval", action="store_true")
    parser.add_argument("--include-document-recognition", action="store_true")
    parser.add_argument("--require-document-created", action="store_true")
    parser.add_argument("--require-visible-created-links", action="store_true")
    parser.add_argument("--auto-confirm", action="store_true")
    parser.add_argument(
        "--document-files",
        default="",
        help="Semicolon list: all=path.pdf or supplier_invoice=path;upd_torg12=path;service_act=path;vat_invoice=path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    apply_profile(args)
    if args.profile == "cloud-fresh":
        env_user = os.getenv("FRESH_CLOUD_USER", "")
        explicit_user = args.user and args.user != "Администратор"
        if not explicit_user and not env_user:
            print(json.dumps({
                "passed": False,
                "error": "Для profile=cloud-fresh задайте --user или FRESH_CLOUD_USER в .env.",
            }, ensure_ascii=False, indent=2))
            return 2
    if args.include_ui:
        args.include_skill_write = True
        args.include_skill_lifecycle = True
        args.include_negative_ui = True
        args.include_result_table_link = True
        args.include_approval = True
        args.include_document_recognition = True
        args.require_visible_created_links = True

    if args.profile == "cloud-fresh":
        # На production Fresh HTTP bridge codex-test обычно недоступен.
        args.include_skill_write = False
        args.include_skill_lifecycle = False
        args.include_approval = False
        args.include_document_recognition = False
        if args.include_ui or args.include_negative_ui:
            args.include_negative_ui = True

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_dir = Path(args.artifact_dir) / ("matrix_" + timestamp)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    if args.profile == "cloud-api":
        if not args.user or not args.password:
            print(json.dumps({
                "passed": False,
                "error": "Для profile=cloud-api задайте --user/--password или FRESH_CLOUD_USER/FRESH_CLOUD_PASSWORD.",
            }, ensure_ascii=False, indent=2))
            return 2
        scenario_wait = args.web_agent_wait_sec if args.web_agent_wait_sec != 180 else 900
        group_size = {
            "smoke": 4,
            "recovery": 2,
            "write": 2,
            "safety": 4,
            "metadata": 2,
            "extended": 13,
        }.get(args.group, 13)
        results.append(run_agent_api_gate(
            "cloud_api",
            args.agent_api_url,
            args.user,
            args.password,
            args.group,
            args.score_mode,
            artifact_dir,
            max(args.gate_timeout_sec, scenario_wait * group_size + 180),
            args.auto_confirm,
            scenario_wait,
        ))
        results.extend(run_agent_api_recognition(
            args.agent_api_url,
            args.user,
            args.password,
            args.document_files,
            artifact_dir,
            scenario_wait,
            args.auto_confirm,
            args.require_document_created,
        ))
    if args.profile == "cloud-fresh":
        results.append(run_web_quality_gate(
            "cloud_fresh",
            args.web_url,
            args.user,
            args.password,
            args.group,
            artifact_dir,
            args.gate_timeout_sec,
            args.web_agent_wait_sec,
            args.auto_confirm,
            args.headed,
        ))
    if not args.skip_bp:
        results.append(run_bridge_gate("bp", args.bp_bridge, args.bp_user, args.group, args.score_mode, artifact_dir, args.gate_timeout_sec))
    if not args.skip_unf:
        results.append(run_bridge_gate("unf", args.unf_bridge, args.unf_user, args.group, args.score_mode, artifact_dir, args.gate_timeout_sec))

    for script, script_args, out_dir, timeout_sec in build_ui_jobs(args, artifact_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        results.append(run_ui_script(script, script_args, out_dir, timeout_sec))

    passed = all(item.get("success") for item in results)
    report = {
        "timestamp": timestamp,
        "artifact_dir": str(artifact_dir),
        "profile": args.profile,
        "web_url": args.web_url if args.profile == "cloud-fresh" else "",
        "agent_api_url": args.agent_api_url if args.profile == "cloud-api" else "",
        "passed": passed,
        "total": len(results),
        "passed_count": sum(1 for item in results if item.get("success")),
        "results": results,
    }
    report_file = artifact_dir / "quality_gate_matrix_report.json"
    report_file.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(json.dumps({
        "passed": passed,
        "total": report["total"],
        "passed_count": report["passed_count"],
        "report_file": str(report_file),
        "failed": [
            {
                "name": item.get("name"),
                "kind": item.get("kind"),
                "returncode": item.get("returncode"),
                "report_file": item.get("report", {}).get("report_file", ""),
            }
            for item in results if not item.get("success")
        ],
    }, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
