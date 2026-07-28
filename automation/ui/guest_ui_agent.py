# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def append_agent_log(path: Path, message: str) -> None:
    ensure_dir(path.parent)
    with path.open("a", encoding="utf-8") as stream:
        stream.write(f"[{utc_now()}] {message}\n")


class GuestUiAgent:
    def __init__(self, jobs_root: Path, poll_sec: float, once: bool) -> None:
        self.jobs_root = jobs_root
        self.poll_sec = poll_sec
        self.once = once
        self.pending_dir = ensure_dir(jobs_root / "pending")
        self.running_dir = ensure_dir(jobs_root / "running")
        self.completed_dir = ensure_dir(jobs_root / "completed")
        self.failed_dir = ensure_dir(jobs_root / "failed")
        self.agent_log = jobs_root / "guest_ui_agent.log"
        self.heartbeat = jobs_root / "guest_ui_agent_heartbeat.json"

    def run(self) -> int:
        append_agent_log(self.agent_log, "guest ui agent started")
        while True:
            self._write_heartbeat()
            job_file = self._claim_next_job()
            if job_file is None:
                if self.once:
                    return 0
                time.sleep(self.poll_sec)
                continue
            self._process_job(job_file)
            if self.once:
                return 0

    def _write_heartbeat(self) -> None:
        payload = {
            "timestamp_utc": utc_now(),
            "jobs_root": str(self.jobs_root),
            "repo_root": str(REPO_ROOT),
            "pid": os.getpid(),
        }
        self.heartbeat.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _claim_next_job(self) -> Path | None:
        for job_file in sorted(self.pending_dir.glob("*.json")):
            target = self.running_dir / job_file.name
            try:
                job_file.replace(target)
                append_agent_log(self.agent_log, f"claimed job {job_file.name}")
                return target
            except OSError:
                continue
        return None

    def _process_job(self, job_file: Path) -> None:
        result: dict[str, object]
        try:
            job = json.loads(job_file.read_text(encoding="utf-8"))
            result = self._execute_job(job)
            target_dir = self.completed_dir if int(result.get("exit_code", 1)) == 0 else self.failed_dir
        except Exception as exc:
            result = {
                "job_id": job_file.stem,
                "status": "agent_error",
                "exit_code": 1,
                "error": str(exc),
                "finished_at_utc": utc_now(),
            }
            target_dir = self.failed_dir
            append_agent_log(self.agent_log, f"job {job_file.name} failed in agent: {exc}")
        result_path = target_dir / job_file.name
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            job_file.unlink()
        except OSError:
            pass

    def _execute_job(self, job: dict[str, object]) -> dict[str, object]:
        run_dir = ensure_dir(Path(str(job["run_dir"])))
        log_file = Path(str(job["log_file"]))
        screenshot_dir = ensure_dir(Path(str(job["screenshot_dir"])))
        launcher_output_log = run_dir / "guest_agent_subprocess.log"
        command = self._build_test_command(job, log_file, screenshot_dir)

        append_agent_log(self.agent_log, f"starting ui test for job {job['job_id']}")
        started_at = utc_now()
        process = subprocess.run(
            command,
            cwd=REPO_ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        finished_at = utc_now()
        if process.stdout:
            launcher_output_log.write_text(process.stdout, encoding="utf-8")
        artifacts = [str(path) for path in sorted(screenshot_dir.glob("*"))]
        if launcher_output_log.exists():
            artifacts.append(str(launcher_output_log))

        return {
            "job_id": job["job_id"],
            "status": "completed" if process.returncode == 0 else "failed",
            "exit_code": process.returncode,
            "started_at_utc": started_at,
            "finished_at_utc": finished_at,
            "run_dir": str(run_dir),
            "log_file": str(log_file),
            "screenshot_dir": str(screenshot_dir),
            "artifacts": artifacts,
        }

    def _build_test_command(
        self,
        job: dict[str, object],
        log_file: Path,
        screenshot_dir: Path,
    ) -> list[str]:
        ui_mode = str(job.get("ui_mode", "desktop")).lower()
        if ui_mode == "web":
            command = [
                sys.executable,
                "-u",
                str(REPO_ROOT / "automation" / "ui" / "web_query1c_test.py"),
                "--web-url",
                str(job.get("web_url", "http://192.168.2.127/fresh-unf")),
                "--chrome-exe",
                str(job.get("chrome_exe", r"C:\Program Files\Google\Chrome\Application\chrome.exe")),
                "--base-path",
                str(job["base_path"]),
                "--user",
                str(job["user"]),
                "--password",
                str(job.get("password", "")),
                "--query-text",
                str(job.get("query_text", "ВЫБРАТЬ 2 КАК Новое")),
                "--query-params-json",
                str(job.get("query_params_json", "")),
                "--expected-text",
                str(job["expected_text"]),
                "--timeout-sec",
                str(job.get("timeout_sec", 180)),
                "--log-file",
                str(log_file),
                "--artifact-dir",
                str(screenshot_dir),
            ]
            if job.get("headed"):
                command.append("--headed")
            return command

        command = [
            sys.executable,
            "-u",
            str(REPO_ROOT / "automation" / "ui" / "ui_1c_agent_test.py"),
            "--platform-exe",
            str(job["platform_exe"]),
            "--base-path",
            str(job["base_path"]),
            "--user",
            str(job["user"]),
            "--dialog-type",
            str(job.get("dialog_type", "Агент")),
            "--test-case",
            str(job.get("test_case", "standard")),
            "--query-text",
            str(job.get("query_text", "ВЫБРАТЬ 2 КАК Новое")),
            "--query-params-json",
            str(job.get("query_params_json", "")),
            "--prompt",
            str(job["prompt"]),
            "--expected-text",
            str(job["expected_text"]),
            "--timeout-sec",
            str(job.get("timeout_sec", 180)),
            "--startup-timeout-sec",
            str(job.get("startup_timeout_sec", 120)),
            "--backend",
            str(job.get("backend", "uia")),
            "--approval-action",
            str(job.get("approval_action", "auto")),
            "--log-file",
            str(log_file),
            "--screenshot-dir",
            str(screenshot_dir),
        ]
        if job.get("require_approval"):
            command.append("--require-approval")
        if job.get("leave_open"):
            command.append("--leave-open")
        return command


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Фоновый агент UI-тестов внутри гостевой Windows VM")
    parser.add_argument(
        "--jobs-root",
        default=r"\\DEV1\D\bsl\AI_agent\automation\logs\vm_ui_jobs",
        help="Каталог очереди UI jobs, доступный и хосту, и гостю",
    )
    parser.add_argument("--poll-sec", type=float, default=2.0)
    parser.add_argument("--once", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.chdir(REPO_ROOT)
    agent = GuestUiAgent(Path(args.jobs_root), args.poll_sec, args.once)
    return agent.run()


if __name__ == "__main__":
    raise SystemExit(main())
