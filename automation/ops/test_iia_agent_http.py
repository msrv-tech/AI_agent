# -*- coding: utf-8 -*-
"""Прогон каждой HTTP-ручки /hs/iia-agent на локальной публикации."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import urllib.error
import urllib.parse
import urllib.request


DEFAULT_BASE = "http://192.168.2.127/fresh-unf/hs/iia-agent"
DEFAULT_USER = "Администратор"


def request(base: str, method: str, path: str, user: str, password: str, body: dict | None = None, timeout: int = 60) -> tuple[int, dict | str]:
    url = base.rstrip("/") + path
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    password_mgr.add_password(None, base, user, password)
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({}),
        urllib.request.HTTPBasicAuthHandler(password_mgr),
    )
    try:
        with opener.open(req, timeout=timeout) as response:
            raw = response.read().decode("utf-8-sig")
            payload: dict | str
            try:
                payload = json.loads(raw) if raw else {}
            except json.JSONDecodeError:
                payload = raw
            return response.status, payload
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8-sig", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"error": raw}
        except json.JSONDecodeError:
            payload = {"error": raw}
        return exc.code, payload


def must(ok: bool, name: str, detail: str = "") -> None:
    if ok:
        print(f"[OK] {name}")
        return
    raise RuntimeError(f"{name}: {detail}")


def run(base: str, user: str, password: str) -> int:
    checked: list[str] = []

    code, health = request(base, "GET", "/health", user, password)
    must(code == 200 and isinstance(health, dict) and health.get("execute_bsl") is False, "GET /health", f"{code} {health}")
    checked.append("GET /health")

    code, me = request(base, "GET", "/v1/me", user, password)
    must(code == 200 and isinstance(me, dict) and me.get("user"), "GET /v1/me", f"{code} {me}")
    must("api_key" not in me and "Provider_ApiKey" not in me, "GET /v1/me no secrets", str(me))
    checked.append("GET /v1/me")

    code, created = request(base, "POST", "/v1/dialogs", user, password, {"type": "agent"})
    must(code in (200, 201) and isinstance(created, dict) and created.get("id"), "POST /v1/dialogs", f"{code} {created}")
    dialog_id = created["id"]
    checked.append("POST /v1/dialogs")

    code, dialogs = request(base, "GET", "/v1/dialogs?limit=5", user, password)
    must(code == 200 and isinstance(dialogs, dict) and any(item.get("id") == dialog_id for item in dialogs.get("dialogs", [])), "GET /v1/dialogs", f"{code} {dialogs}")
    checked.append("GET /v1/dialogs")

    code, state = request(base, "GET", f"/v1/dialogs/{dialog_id}", user, password)
    must(code == 200 and isinstance(state, dict) and "why_stopped" in state and "tokens" in state, "GET /v1/dialogs/{id}", f"{code} {state}")
    checked.append("GET /v1/dialogs/{id}")

    code, log = request(base, "GET", f"/v1/dialogs/{dialog_id}/log", user, password)
    must(code == 200 and isinstance(log, dict) and "log" in log and "total_length" in log, "GET /v1/dialogs/{id}/log", f"{code} {log}")
    offset = log.get("total_length", 0)
    code, log_tail = request(base, "GET", f"/v1/dialogs/{dialog_id}/log?offset={offset}", user, password)
    must(code == 200 and isinstance(log_tail, dict) and log_tail.get("offset") == offset, "GET /v1/dialogs/{id}/log?offset", f"{code} {log_tail}")
    checked.append("GET /v1/dialogs/{id}/log")

    pdf = base64.b64encode(b"%PDF-1.4\nhttp-api-test").decode("ascii")
    code, attached = request(base, "POST", f"/v1/dialogs/{dialog_id}/attachments", user, password, {"file_name": "http-api-test.pdf", "content_base64": pdf})
    must(code in (200, 201) and isinstance(attached, dict) and attached.get("attachment_id"), "POST /v1/dialogs/{id}/attachments", f"{code} {attached}")
    code, attachments = request(base, "GET", f"/v1/dialogs/{dialog_id}/attachments", user, password)
    must(code == 200 and isinstance(attachments, dict) and attachments.get("attachments"), "GET /v1/dialogs/{id}/attachments", f"{code} {attachments}")
    checked.append("GET|POST /v1/dialogs/{id}/attachments")

    code, empty_send = request(base, "POST", f"/v1/dialogs/{dialog_id}/send", user, password, {"text": ""})
    must(code == 400, "POST /v1/dialogs/{id}/send empty", f"{code} {empty_send}")
    code, sent = request(base, "POST", f"/v1/dialogs/{dialog_id}/send", user, password, {"text": "HTTP API тест: остановись сразу"})
    must(code in (200, 202) and isinstance(sent, dict) and sent.get("id") == dialog_id, "POST /v1/dialogs/{id}/send", f"{code} {sent}")
    checked.append("POST /v1/dialogs/{id}/send")

    code, stopped = request(base, "POST", f"/v1/dialogs/{dialog_id}/stop", user, password, {})
    must(code == 200 and isinstance(stopped, dict) and stopped.get("orchestrator_running") is False, "POST /v1/dialogs/{id}/stop", f"{code} {stopped}")
    checked.append("POST /v1/dialogs/{id}/stop")

    code, bad_confirm = request(base, "POST", f"/v1/dialogs/{dialog_id}/confirm", user, password, {"action": "unknown-action"})
    must(code == 400, "POST /v1/dialogs/{id}/confirm unknown", f"{code} {bad_confirm}")
    checked.append("POST /v1/dialogs/{id}/confirm")

    for path, key in (
        (f"/v1/dialogs/{dialog_id}/why-stopped", "why_stopped"),
        (f"/v1/dialogs/{dialog_id}/metrics", "metrics"),
        (f"/v1/dialogs/{dialog_id}/trace?limit=10", "events"),
        (f"/v1/dialogs/{dialog_id}/timeline?limit=10", "timeline"),
        (f"/v1/dialogs/{dialog_id}/failures?limit=5", "failures"),
        (f"/v1/dialogs/{dialog_id}/checkpoints?limit=10", "checkpoints"),
        (f"/v1/dialogs/{dialog_id}/checkpoints/diff", "diff"),
        (f"/v1/dialogs/{dialog_id}/objects", "objects"),
        (f"/v1/dialogs/{dialog_id}/query-result?limit=5", "rows"),
        ("/v1/event-log?minutes=10&limit=10", "events"),
        ("/v1/rag/status", "indexes"),
    ):
        code, payload = request(base, "GET", path, user, password)
        must(code == 200 and isinstance(payload, dict) and key in payload, f"GET {path}", f"{code} {payload}")
        checked.append(f"GET {path.split('?')[0]}")

    code, resume = request(base, "POST", f"/v1/dialogs/{dialog_id}/resume", user, password, {"checkpoint_index": -1, "auto_start": False})
    must(code in (200, 202) and isinstance(resume, dict) and resume.get("id") == dialog_id, "POST /v1/dialogs/{id}/resume", f"{code} {resume}")
    code, bad_index = request(base, "POST", f"/v1/dialogs/{dialog_id}/resume", user, password, {"checkpoint_index": 99999, "auto_start": False})
    must(code in (400, 500) and isinstance(bad_index, dict) and bad_index.get("error"), "POST /v1/dialogs/{id}/resume bad-index", f"{code} {bad_index}")

    code, empty_dialog = request(base, "POST", "/v1/dialogs", user, password, {"type": "agent"})
    must(code in (200, 201) and isinstance(empty_dialog, dict) and empty_dialog.get("id"), "POST /v1/dialogs empty-for-resume", f"{code} {empty_dialog}")
    code, empty_resume = request(base, "POST", f"/v1/dialogs/{empty_dialog['id']}/resume", user, password, {"checkpoint_index": -1, "auto_start": False})
    must(code in (400, 500) and isinstance(empty_resume, dict) and empty_resume.get("error"), "POST /v1/dialogs/{id}/resume empty", f"{code} {empty_resume}")
    checked.append("POST /v1/dialogs/{id}/resume")

    print()
    print("--- Итого ---")
    print(f"Проверено ручек: {len(checked)}")
    for name in checked:
        print(f"  {name}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Прогон HTTP API агента")
    parser.add_argument("--base-url", default=DEFAULT_BASE)
    parser.add_argument("--user", default=DEFAULT_USER)
    parser.add_argument("--password", default="")
    args = parser.parse_args()
    try:
        return run(args.base_url, args.user, args.password)
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
