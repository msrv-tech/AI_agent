# -*- coding: utf-8 -*-
"""Клиент закрытого HTTP API /hs/iia-agent. Произвольный BSL не вызывается."""

from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


SUMMARY_MARKER = "=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ==="
SUMMARY_NOT_FORMED = "Резюме не сформировано"


class AgentApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None, payload: Any = None):
        super().__init__(message)
        self.status = status
        self.payload = payload


def api_dialog_type(dialog_type: str) -> str:
    key = (dialog_type or "").strip().casefold()
    if key in {"запрос1с", "query1c", "zapros1s"}:
        return "query1c"
    if key in {"распознаваниедокументов", "document_recognition"}:
        return "document_recognition"
    if key in {"agent", "агент", ""}:
        return "agent"
    raise AgentApiError(f"Неизвестный тип диалога: {dialog_type}")


UNF_RECOGNITION_CASES = {
    "supplier_invoice": {
        "id": "supplier_invoice",
        "prompt": "распознай счет поставщика по приложенному файлу и подготовь документ в базе",
        "expected_skill": "recognize-supplier-invoice",
        "expected_target": "СчетНаОплатуПоставщика",
    },
    "upd_torg12": {
        "id": "upd_torg12",
        "prompt": "распознай УПД или ТОРГ-12 по приложенному файлу и подготовь документ поступления",
        "expected_skill": "recognize-upd-torg12",
        "expected_target": "ПриходнаяНакладная",
    },
    "service_act": {
        "id": "service_act",
        "prompt": "распознай акт услуг по приложенному файлу и подготовь документ поступления услуг",
        "expected_skill": "recognize-service-act",
        "expected_target": "АктВыполненныхРабот",
    },
    "vat_invoice": {
        "id": "vat_invoice",
        "prompt": "распознай счет-фактуру по приложенному файлу и подготовь документ в базе",
        "expected_skill": "recognize-invoice-factura",
        "expected_target": "СчетФактураПолученный",
    },
}


def evaluate_recognition(log_text: str, file_name: str, skill: str, target: str, objects: list, require_created: bool) -> dict:
    log = log_text or ""
    object_count = len(objects or [])
    template_applied = "Использован DSL template выбранного skill распознавания" in log
    checks = {
        "recognition_mode": "РЕЖИМ: РАСПОЗНАВАНИЕ ДОКУМЕНТОВ" in log or template_applied,
        "skill": skill in log,
        "attachment": file_name in log,
        "target": (
            f"target_object_name={target}" in log
            or f'"document_type": "{target}"' in log
            or f"Создан документ '{target}'" in log
        ),
        "dsl_template": "DSL_TEMPLATE_JSON" in log or template_applied,
        "provider_ok": "Ошибка API (" not in log and "OpenAI API error" not in log,
    }
    if require_created:
        checks["created_document"] = object_count > 0 or "Создан черновик документа" in log or "DSL Result: ok | CreateDocument" in log
    return {
        "checks": checks,
        "passed": all(checks.values()),
        "object_count": object_count,
    }


def infer_task_success(log_text: str) -> tuple[bool, str]:
    """Успех задачи по фактам из лога. Статус проверки в API 0.9.11 отдельно не отдаётся."""
    text = log_text or ""
    postconditions = re.findall(r"\[POSTCONDITION\]\s+success=(true|false)", text, flags=re.I)
    if postconditions:
        return postconditions[-1].lower() == "true", "postcondition"
    if "Проверка наличия вывода данных: ДА" in text:
        return True, "query_output"
    if "Проверка наличия вывода данных: НЕТ" in text:
        return False, "query_output_missing"
    if SUMMARY_MARKER in text and SUMMARY_NOT_FORMED not in text:
        return True, "summary"
    return False, "task_status_unavailable"


class AgentApiClient:
    def __init__(self, base_url: str, user: str, password: str, timeout_sec: int = 60):
        if not base_url:
            raise AgentApiError("Не задан URL HTTP API агента.")
        if not user:
            raise AgentApiError("Не задан пользователь HTTP API агента.")
        self.base_url = base_url.rstrip("/")
        self.user = user
        self.password = password or ""
        self.timeout_sec = timeout_sec

    def request(self, method: str, path: str, body: dict | None = None, timeout_sec: int | None = None) -> tuple[int, Any]:
        url = self.base_url + path
        data = None
        headers = {"Accept": "application/json"}
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, self.base_url, self.user, self.password)
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPBasicAuthHandler(password_mgr),
        )
        try:
            with opener.open(req, timeout=timeout_sec or self.timeout_sec) as response:
                raw = response.read().decode("utf-8-sig")
                payload = json.loads(raw) if raw else {}
                return response.status, payload
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8-sig", errors="replace")
            try:
                payload = json.loads(raw) if raw else {"error": raw}
            except json.JSONDecodeError:
                payload = {"error": raw}
            message = payload.get("error") if isinstance(payload, dict) else raw
            raise AgentApiError(f"HTTP {exc.code} {method} {path}: {message}", exc.code, payload) from exc

    def preflight(self) -> dict:
        code, health = self.request("GET", "/health")
        if code != 200 or not isinstance(health, dict):
            raise AgentApiError(f"GET /health вернул {code}: {health}", code, health)
        if health.get("execute_bsl") is not False:
            raise AgentApiError("GET /health: execute_bsl должен быть false", code, health)
        me_code, me = self.request("GET", "/v1/me")
        if me_code != 200 or not isinstance(me, dict) or not me.get("user"):
            raise AgentApiError(f"GET /v1/me вернул {me_code}: {me}", me_code, me)
        if "api_key" in me or "Provider_ApiKey" in me:
            raise AgentApiError("GET /v1/me вернул секрет", me_code, {"keys": list(me)})
        return {"health": health, "me": me}

    def attach_file(self, dialog_id: str, file_path: str) -> dict:
        path = Path(file_path)
        if not path.is_file():
            raise AgentApiError(f"Файл для распознавания не найден: {path}")
        content = path.read_bytes()
        if not content:
            raise AgentApiError(f"Файл для распознавания пуст: {path}")
        code, payload = self.request(
            "POST",
            f"/v1/dialogs/{dialog_id}/attachments",
            {"file_name": path.name, "content_base64": base64.b64encode(content).decode("ascii")},
            timeout_sec=120,
        )
        if code not in (200, 201) or not isinstance(payload, dict) or not payload.get("attachment_id"):
            raise AgentApiError(f"POST attachments вернул {code}: {payload}", code, payload)
        return payload

    def dialog_objects(self, dialog_id: str) -> list:
        code, payload = self.request("GET", f"/v1/dialogs/{dialog_id}/objects")
        if code != 200 or not isinstance(payload, dict) or "objects" not in payload:
            raise AgentApiError(f"GET objects вернул {code}: {payload}", code, payload)
        objects = payload.get("objects")
        if not isinstance(objects, list):
            raise AgentApiError(f"GET objects вернул не список: {payload}", code, payload)
        return objects

    def run_dialog(
        self,
        text: str,
        dialog_type: str,
        auto_confirm: bool = False,
        wait_timeout_sec: int = 900,
        poll_sec: int = 5,
        attachment_path: str = "",
    ) -> dict:
        created_code, created = self.request("POST", "/v1/dialogs", {"type": api_dialog_type(dialog_type)})
        if created_code not in (200, 201) or not isinstance(created, dict) or not created.get("id"):
            raise AgentApiError(f"POST /v1/dialogs вернул {created_code}: {created}", created_code, created)
        dialog_id = str(created["id"])
        if attachment_path:
            self.attach_file(dialog_id, attachment_path)
        send_code, sent = self.request(
            "POST",
            f"/v1/dialogs/{dialog_id}/send",
            {"text": text, "type": api_dialog_type(dialog_type)},
            timeout_sec=120,
        )
        if send_code not in (200, 202) or not isinstance(sent, dict):
            raise AgentApiError(f"POST /v1/dialogs/{{id}}/send вернул {send_code}: {sent}", send_code, sent)

        deadline = time.time() + wait_timeout_sec
        confirms = 0
        state = sent
        timed_out = False
        while time.time() < deadline:
            if not state.get("orchestrator_running"):
                confirmation = state.get("confirmation") or {}
                if auto_confirm and confirmation.get("pending") and confirms < 3:
                    confirms += 1
                    confirm_code, state = self.request(
                        "POST",
                        f"/v1/dialogs/{dialog_id}/confirm",
                        {"action": "approve_without_confirmation"},
                        timeout_sec=120,
                    )
                    if confirm_code not in (200, 202):
                        raise AgentApiError(
                            f"POST confirm вернул {confirm_code}: {state}",
                            confirm_code,
                            state,
                        )
                    continue
                break
            time.sleep(poll_sec)
            state_code, state = self.request("GET", f"/v1/dialogs/{dialog_id}")
            if state_code != 200 or not isinstance(state, dict):
                raise AgentApiError(f"GET /v1/dialogs/{{id}} вернул {state_code}: {state}", state_code, state)
        else:
            timed_out = bool(state.get("orchestrator_running"))

        if state.get("orchestrator_running"):
            stop_code, stopped = self.request("POST", f"/v1/dialogs/{dialog_id}/stop", {})
            if stop_code != 200:
                raise AgentApiError(f"POST stop после таймаута вернул {stop_code}: {stopped}", stop_code, stopped)
            state = stopped
            timed_out = True

        log_code, log_payload = self.request("GET", f"/v1/dialogs/{dialog_id}/log?limit=200000&offset=0", timeout_sec=120)
        if log_code != 200 or not isinstance(log_payload, dict) or "log" not in log_payload:
            raise AgentApiError(f"GET log вернул {log_code}: {log_payload}", log_code, log_payload)
        if log_payload.get("truncated"):
            raise AgentApiError(
                f"Лог диалога {dialog_id} обрезан (total_length={log_payload.get('total_length')}), оценка по хвосту запрещена",
                log_code,
                {"id": dialog_id, "total_length": log_payload.get("total_length")},
            )
        log_text = str(log_payload.get("log") or "")
        query_code, query_payload = self.request("GET", f"/v1/dialogs/{dialog_id}/query-result?limit=5")
        if query_code != 200 or not isinstance(query_payload, dict) or "row_count" not in query_payload:
            raise AgentApiError(f"GET query-result вернул {query_code}: {query_payload}", query_code, query_payload)

        success, success_source = infer_task_success(log_text)
        if timed_out:
            success = False
            log_text += f"\n[ОШИБКА] timeout waiting orchestrator after {wait_timeout_sec}s"
        confirmation = state.get("confirmation") or {}
        return {
            "Успех": success,
            "task_success_source": success_source,
            "Лог": log_text,
            "UsageTokens": int(state.get("tokens") or 0),
            "СсылкаДиалога": dialog_id,
            "approval_pending": bool(confirmation.get("pending")),
            "query_row_count": int(query_payload.get("row_count") or 0),
            "why_stopped": state.get("why_stopped"),
            "timeout": timed_out,
            "write_enabled_irrelevant": True,
        }

    def run_recognition_case(self, case: dict, file_path: str, auto_confirm: bool = True, wait_timeout_sec: int = 900, require_created: bool = False) -> dict:
        result = self.run_dialog(
            case["prompt"],
            "document_recognition",
            auto_confirm=auto_confirm,
            wait_timeout_sec=wait_timeout_sec,
            attachment_path=file_path,
        )
        objects = self.dialog_objects(str(result["СсылкаДиалога"]))
        evaluation = evaluate_recognition(
            str(result.get("Лог") or ""),
            Path(file_path).name,
            case["expected_skill"],
            case["expected_target"],
            objects,
            require_created,
        )
        return {
            "id": case["id"],
            "dialog_id": result["СсылкаДиалога"],
            "file_name": Path(file_path).name,
            "skill": case["expected_skill"],
            "target": case["expected_target"],
            "tokens": result.get("UsageTokens"),
            "timeout": bool(result.get("timeout")),
            "objects": objects,
            "log": result.get("Лог") or "",
            **evaluation,
        }
