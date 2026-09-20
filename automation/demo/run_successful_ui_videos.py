# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", required=True, help="report.json from run_followup_bridge.py")
    parser.add_argument("--scenarios", default=str(Path(__file__).with_name("followup_scenarios.json")))
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--windows-compatible", action="store_true")
    args = parser.parse_args()

    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    scenarios = {item["id"]: item for item in json.loads(Path(args.scenarios).read_text(encoding="utf-8"))}
    successful = [item["id"] for item in report["results"] if item.get("success")]
    if args.limit:
        successful = successful[: args.limit]

    ps1 = ROOT / "automation" / "ui" / "start_guest_desktop_ffmpeg.ps1"
    powershell = os.path.join(
        os.environ.get("SystemRoot", r"C:\Windows"),
        "System32",
        "WindowsPowerShell",
        "v1.0",
        "powershell.exe",
    )
    for scenario_id in successful:
        scenario = scenarios[scenario_id]
        cmd = [
            powershell,
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps1),
            "-TestCase",
            "standard",
            "-Prompt",
            scenario["prompt"],
            "-DialogType",
            "Запрос1С",
            "-FollowupsJson",
            json.dumps(scenario.get("followups", []), ensure_ascii=False),
            "-ShowQueryBetweenTurns",
            "-MouseControl",
            "-ExpectedText",
            "Задача выполнена успешно",
            "-TimeoutSec",
            "900",
            "-RecordDurationSec",
            "0",
        ]
        if args.windows_compatible:
            cmd.append("-WindowsCompatible")
        print("\n== UI video:", scenario_id, "==")
        completed = subprocess.run(cmd, cwd=str(ROOT))
        if completed.returncode != 0:
            print("UI video failed:", scenario_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
