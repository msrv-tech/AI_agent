# -*- coding: utf-8 -*-
"""Release quality gate runner for the 1C AI Agent.

Runs the reusable COM scenarios against one or more configurations and,
optionally, browser/bridge E2E tests for skills, write flow, negative UI and
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
DEFAULT_BP = 'Srvr="192.168.2.126:2541";Ref="fresh-bp-demo";Usr="Администратор";Pwd="";'
DEFAULT_UNF = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";Usr="Администратор";Pwd="";'
DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"


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
        "expected_skill": "recognize-vat-invoice",
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


def run_com_gate(name: str, connection: str, group: str, score_mode: str, artifact_dir: Path, timeout_sec: int) -> dict:
    log_dir = artifact_dir / "com" / name
    log_dir.mkdir(parents=True, exist_ok=True)
    cmd = [
        sys.executable,
        "automation/com_1c/test_examples.py",
        "--connection",
        connection,
        "--examples-group",
        group,
        "--score-mode",
        score_mode,
        "--log-dir",
        str(log_dir),
    ]
    result = run_command(cmd, timeout_sec)
    result["name"] = name
    result["kind"] = "com_examples"
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
            if args.auto_confirm:
                case_args.append("--auto-confirm")
            jobs.append((
                "automation/ui/web_document_recognition_e2e.py",
                case_args,
                artifact_dir / "ui" / "document_recognition" / case_id,
                args.ui_timeout_sec + 180,
            ))
    return jobs


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Release quality gate matrix for 1C AI Agent")
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "quality_gate_matrix"))
    parser.add_argument("--group", default="extended", help="test_examples group: smoke|recovery|write|safety|metadata|extended")
    parser.add_argument("--score-mode", default="heuristic", choices=["heuristic", "llm", "hybrid"])
    parser.add_argument("--bp-connection", default=DEFAULT_BP)
    parser.add_argument("--unf-connection", default=DEFAULT_UNF)
    parser.add_argument("--skip-bp", action="store_true")
    parser.add_argument("--skip-unf", action="store_true")
    parser.add_argument("--com-timeout-sec", type=int, default=1200)
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--ui-timeout-sec", type=int, default=90)
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--include-ui", action="store_true", help="Enable all default UI/E2E suites")
    parser.add_argument("--include-skill-write", action="store_true")
    parser.add_argument("--include-skill-lifecycle", action="store_true")
    parser.add_argument("--include-negative-ui", action="store_true")
    parser.add_argument("--include-approval", action="store_true")
    parser.add_argument("--include-document-recognition", action="store_true")
    parser.add_argument("--require-document-created", action="store_true")
    parser.add_argument("--auto-confirm", action="store_true")
    parser.add_argument(
        "--document-files",
        default="",
        help="Semicolon list: all=path.pdf or supplier_invoice=path;upd_torg12=path;service_act=path;vat_invoice=path",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.include_ui:
        args.include_skill_write = True
        args.include_skill_lifecycle = True
        args.include_negative_ui = True
        args.include_approval = True
        args.include_document_recognition = True

    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_dir = Path(args.artifact_dir) / ("matrix_" + timestamp)
    artifact_dir.mkdir(parents=True, exist_ok=True)

    results: list[dict] = []
    if not args.skip_bp:
        results.append(run_com_gate("bp", args.bp_connection, args.group, args.score_mode, artifact_dir, args.com_timeout_sec))
    if not args.skip_unf:
        results.append(run_com_gate("unf", args.unf_connection, args.group, args.score_mode, artifact_dir, args.com_timeout_sec))

    for script, script_args, out_dir, timeout_sec in build_ui_jobs(args, artifact_dir):
        out_dir.mkdir(parents=True, exist_ok=True)
        results.append(run_ui_script(script, script_args, out_dir, timeout_sec))

    passed = all(item.get("success") for item in results)
    report = {
        "timestamp": timestamp,
        "artifact_dir": str(artifact_dir),
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
