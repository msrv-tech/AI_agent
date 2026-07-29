# -*- coding: utf-8 -*-
"""Run ИИА_Тесты tests through the HTTP bridge, without COM."""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request


DEFAULT_BRIDGE_URL = "http://192.168.2.127/fresh-unf/hs/codex-test/command"


def bsl_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def bridge_execute(bridge_url: str, code: str, timeout_sec: int = 180) -> object:
    body = json.dumps({"command": "ExecuteBSL", "code": code, "params": []}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        bridge_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8-sig", errors="replace")
        raise RuntimeError(f"Bridge HTTP {error.code}: {details}") from error
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload.get("result")


def run_test(bridge_url: str, test_name: str) -> dict:
    if not re.fullmatch(r"[A-Za-zА-Яа-яЁё0-9_]+", test_name):
        raise ValueError("Unsafe test name: " + test_name)
    code = "РезультатВыполнения = ИИА_Тесты." + test_name + "();"
    result = bridge_execute(bridge_url, code)
    if isinstance(result, dict):
        return result
    return {"Успех": False, "Сообщение": "Unexpected bridge result", "raw": repr(result)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one or more ИИА_Тесты tests through bridge")
    parser.add_argument("tests", nargs="+")
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--timeout-sec", type=int, default=180)
    args = parser.parse_args()

    all_ok = True
    results: list[dict] = []
    for test_name in args.tests:
        result = run_test(args.bridge_url, test_name)
        result["ИмяТеста"] = test_name
        results.append(result)
        ok = bool(result.get("Успех"))
        all_ok = all_ok and ok
        print(("OK   " if ok else "FAIL ") + test_name + ": " + str(result.get("Сообщение", "")))
        details = result.get("Детали")
        if details:
            for item in details:
                print("  " + str(item))
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
