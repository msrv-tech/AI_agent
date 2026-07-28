# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import uuid
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from com_1c import call_procedure, connect_to_1c, get_enum_value


DEFAULT_HOST_JOBS_ROOT = REPO_ROOT / "automation" / "logs" / "vm_ui_jobs"
DEFAULT_GUEST_JOBS_ROOT = r"\\DEV1\D\bsl\AI_agent\automation\logs\vm_ui_jobs"
HOST_PREPARED_QUERY1C_MARKER = "__HOST_PREPARED_QUERY1C__"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'
DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"


def _parse_1c_connection_string(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, raw in re.findall(r"([A-Za-zА-Яа-я0-9_]+)\s*=\s*(\"(?:[^\"]|\"\")*\"|[^;]*)\s*;?", value or ""):
        item = raw.strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1].replace('""', '"')
        result[key.lower()] = item
    return result


def _com_connection_string(base_path: str, user: str, password: str) -> str:
    parts = _parse_1c_connection_string(base_path)
    if parts:
        parts["usr"] = user
        parts["pwd"] = password
        ordered_keys = ["file", "srvr", "ref", "usr", "pwd"]
        keys = [key for key in ordered_keys if key in parts] + [
            key for key in parts if key not in ordered_keys
        ]
        names = {
            "file": "File",
            "srvr": "Srvr",
            "ref": "Ref",
            "usr": "Usr",
            "pwd": "Pwd",
        }
        return "".join(f'{names.get(key, key)}="{parts[key]}";' for key in keys)
    return f'File="{base_path}";Usr="{user}";Pwd="{password}";'


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def build_job(args: argparse.Namespace, job_id: str, run_dir: Path) -> dict[str, object]:
    prompt = args.prompt
    if args.prepare_query1c_on_host and HOST_PREPARED_QUERY1C_MARKER not in prompt:
        prompt = f"{prompt} {HOST_PREPARED_QUERY1C_MARKER}".strip()
    return {
        "job_id": job_id,
        "created_at_local": datetime.now().isoformat(),
        "ui_mode": args.ui_mode,
        "platform_exe": args.platform_exe,
        "base_path": args.base_path,
        "user": args.user,
        "password": args.password,
        "prompt": prompt,
        "dialog_type": args.dialog_type,
        "expected_text": args.expected_text,
        "timeout_sec": args.timeout_sec,
        "startup_timeout_sec": args.startup_timeout_sec,
        "backend": args.backend,
        "approval_action": args.approval_action,
        "require_approval": args.require_approval,
        "leave_open": args.leave_open,
        "test_case": args.test_case,
        "query_text": args.query_text,
        "query_params_json": args.query_params_json,
        "web_url": args.web_url,
        "chrome_exe": args.chrome_exe,
        "headed": args.headed,
        "skip_com_prepare": args.prepare_query1c_on_host,
        "run_dir": str(run_dir),
        "log_file": str(run_dir / "ui_test.log"),
        "screenshot_dir": str(run_dir / "artifacts"),
    }


def wait_for_result(host_jobs_root: Path, job_id: str, timeout_sec: int) -> Path:
    completed = host_jobs_root / "completed" / f"{job_id}.json"
    failed = host_jobs_root / "failed" / f"{job_id}.json"
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if completed.exists():
            return completed
        if failed.exists():
            return failed
        time.sleep(2)
    raise TimeoutError(f"Не дождались завершения VM UI job {job_id}")


def prepare_query1c_dialog_on_host(args: argparse.Namespace) -> None:
    connection_string = _com_connection_string(args.base_path, args.user, args.password)
    connection = connect_to_1c(connection_string)
    if not connection:
        raise RuntimeError("Не удалось открыть COM-подключение к 1С на хосте для подготовки Query1C.")
    dialog_type = get_enum_value(connection, "ИИА_ТипДиалога", "Запрос1С")
    if dialog_type is None:
        raise RuntimeError("Не найдено перечисление ИИА_ТипДиалога.Запрос1С на хосте.")
    dialog_ref = call_procedure(
        connection,
        "ИИА_Сервер",
        "СоздатьНовыйДиалог",
        args.user,
        dialog_type,
    )
    if dialog_ref is None:
        raise RuntimeError("Хост не получил ссылку на диалог Query1C.")
    call_procedure(
        connection,
        "ИИА_Сервер",
        "СохранитьЧерновикЗапроса1С",
        dialog_ref,
        args.query_text,
        args.query_params_json,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Запуск UI-теста 1С через гостевого VM-агента")
    parser.add_argument("--ui-mode", default="desktop", choices=["desktop", "web"])
    parser.add_argument("--prompt", default="какие поля есть у справочника Контрагенты")
    parser.add_argument("--expected-text", default="Поля успешно получены")
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--startup-timeout-sec", type=int, default=120)
    parser.add_argument("--backend", default="uia", choices=["uia", "win32"])
    parser.add_argument("--approval-action", default="auto", choices=["auto", "approve", "without_confirmation"])
    parser.add_argument("--require-approval", action="store_true")
    parser.add_argument("--platform-exe", default=r"C:\Tools\1cv8\8.5.1.1150\bin\1cv8.exe")
    parser.add_argument("--base-path", default=DEFAULT_CONNECTION_STRING)
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--dialog-type", default="Агент")
    parser.add_argument("--test-case", default="standard", choices=["standard", "query1c_form", "web_query1c", "desktop_diag"])
    parser.add_argument("--query-text", default="ВЫБРАТЬ 2 КАК Новое")
    parser.add_argument("--query-params-json", default="")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--prepare-query1c-on-host", action="store_true")
    parser.add_argument("--leave-open", action="store_true")
    parser.add_argument("--wait-timeout-sec", type=int, default=600)
    parser.add_argument("--host-jobs-root", default=str(DEFAULT_HOST_JOBS_ROOT))
    parser.add_argument("--guest-jobs-root", default=DEFAULT_GUEST_JOBS_ROOT)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.prepare_query1c_on_host:
        prepare_query1c_dialog_on_host(args)
    host_jobs_root = ensure_dir(Path(args.host_jobs_root))
    ensure_dir(host_jobs_root / "pending")
    ensure_dir(host_jobs_root / "running")
    ensure_dir(host_jobs_root / "completed")
    ensure_dir(host_jobs_root / "failed")
    ensure_dir(host_jobs_root / "runs")

    job_id = f"{timestamp()}_{uuid.uuid4().hex[:8]}"
    guest_run_dir = Path(args.guest_jobs_root) / "runs" / job_id
    job = build_job(args, job_id, guest_run_dir)
    pending_job_path = host_jobs_root / "pending" / f"{job_id}.json"
    pending_job_path.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"VM UI job queued: {job_id}")
    print(f"Pending file: {pending_job_path}")
    print("Waiting for guest agent...")

    try:
        result_path = wait_for_result(host_jobs_root, job_id, args.wait_timeout_sec)
    except TimeoutError as exc:
        print(str(exc), file=sys.stderr)
        print(f"Host jobs root: {host_jobs_root}", file=sys.stderr)
        return 2

    result = json.loads(result_path.read_text(encoding="utf-8"))
    print(f"Result file: {result_path}")
    print(f"Status: {result.get('status')}")
    print(f"Exit code: {result.get('exit_code')}")
    print(f"Log file: {result.get('log_file')}")
    print(f"Artifacts dir: {result.get('screenshot_dir')}")
    if result.get("artifacts"):
        print("Artifacts:")
        for artifact in result["artifacts"]:
            print(f"  {artifact}")
    return int(result.get("exit_code", 1))


if __name__ == "__main__":
    raise SystemExit(main())
