# -*- coding: utf-8 -*-
"""
Bridge-слой между внешним benchmark runner и 1С-агентом.

Поддерживает два режима:
    - stateless replay: собирает prompt из всей истории и вызывает
      СоздатьДиалогИВыполнитьАгентаСинхронно;
    - session mode: работает turn-by-turn через HTTP-bridge entrypoints
      СоздатьBridgeСессию / ВыполнитьХодBridge / ЗакрытьBridgeСессию.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_AUTOMATION_DIR = _SCRIPT_DIR.parent
_REPO_ROOT = _AUTOMATION_DIR.parent
for _path in (str(_SCRIPT_DIR), str(_AUTOMATION_DIR), str(_REPO_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from automation.bridge.client import bsl_string, call_exported, execute_bsl  # noqa: E402
from automation.bridge.config import get_bridge_url, setup_console_encoding  # noqa: E402


DEFAULT_SYSTEM_PREFIX = (
    "Ты работаешь как bridge-агент внутри внешнего benchmark.\n"
    "Ниже дана полная история диалога между пользователем и агентом.\n"
    "Нужно ответить на последнее сообщение пользователя, соблюдая ограничения системы 1С.\n"
    "Если действие небезопасно или недоступно, явно сообщи об этом."
)


def _get(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    try:
        return getattr(obj, name, default)
    except Exception:
        return default


@dataclass
class BridgeConfig:
    bridge_url: str
    user: str = "Администратор"
    dialog_type: str = "Агент"
    system_prefix: str = DEFAULT_SYSTEM_PREFIX
    max_prompt_chars: int = 16000
    max_log_chars: int = 12000
    use_sessions: bool = True
    bridge_mode: str = "text"


@dataclass
class BridgeRequest:
    task_id: str
    user_message: str
    conversation: list[dict]
    metadata: dict


@dataclass
class BridgeResponse:
    ok: bool
    task_id: str
    user_message: str
    prompt_text: str
    agent_success: bool
    agent_reply: str
    dialog_ref: str
    usage_tokens: int
    log_excerpt: str
    session_id: str = ""
    error: str = ""


def load_bridge_config(config_path: str | None, bridge_override: str | None) -> BridgeConfig:
    raw = {}
    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            raw = json.load(f)

    bridge_url = get_bridge_url(bridge_override or raw.get("bridge_url"))
    return BridgeConfig(
        bridge_url=bridge_url,
        user=raw.get("user", "Администратор"),
        dialog_type=raw.get("dialog_type", "Агент"),
        system_prefix=raw.get("system_prefix", DEFAULT_SYSTEM_PREFIX),
        max_prompt_chars=int(raw.get("max_prompt_chars", 16000)),
        max_log_chars=int(raw.get("max_log_chars", 12000)),
        use_sessions=bool(raw.get("use_sessions", True)),
        bridge_mode=str(raw.get("bridge_mode", "text")),
    )


def load_request(
    request_path: str | None,
    text: str | None,
    task_id: str,
    history_path: str | None,
) -> BridgeRequest:
    if request_path:
        with open(request_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
        return BridgeRequest(
            task_id=str(raw.get("task_id") or task_id),
            user_message=str(raw.get("user_message") or ""),
            conversation=list(raw.get("conversation") or []),
            metadata=dict(raw.get("metadata") or {}),
        )

    conversation = []
    if history_path:
        with open(history_path, "r", encoding="utf-8") as f:
            history_raw = json.load(f)
        if isinstance(history_raw, list):
            conversation = history_raw

    return BridgeRequest(
        task_id=task_id,
        user_message=text or "",
        conversation=conversation,
        metadata={},
    )


def _normalize_role(role: str) -> str:
    value = (role or "").strip().lower()
    if value in {"assistant", "agent"}:
        return "assistant"
    return "user"


def build_prompt(request: BridgeRequest, config: BridgeConfig) -> str:
    parts = [config.system_prefix.strip()]
    if config.bridge_mode == "tool_json":
        parts.extend(
            [
                "",
                "Если требуется вызвать внешний инструмент benchmark-среды, верни только JSON без пояснений.",
                'Формат: {"tool_calls":[{"name":"tool_name","arguments":{...}}]}',
                "Если инструмент не нужен, верни обычный текстовый ответ пользователю.",
            ]
        )

    parts.extend(["", "История диалога:"])
    for index, item in enumerate(request.conversation, start=1):
        role = _normalize_role(str(item.get("role", "user")))
        content = str(item.get("content", "")).strip()
        if not content:
            continue
        parts.append(f"{index}. {role}: {content}")

    if request.user_message.strip():
        parts.append("")
        parts.append("Последнее сообщение пользователя:")
        parts.append(request.user_message.strip())

    prompt = "\n".join(parts).strip()
    if len(prompt) > config.max_prompt_chars:
        prompt = prompt[-config.max_prompt_chars:]
    return prompt


def _dialog_enum_name(dialog_type: str) -> str:
    type_map = {
        "Agent": "Агент",
        "Агент": "Агент",
        "Запрос1С": "Запрос1С",
        "Zapros1S": "Запрос1С",
    }
    return type_map.get(dialog_type, "Агент")


def _extract_agent_reply(log_text: str) -> str:
    if not log_text:
        return ""

    markers = [
        "=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ===",
        "--- Итоговый ответ ---",
        "Итоговый ответ:",
    ]
    for marker in markers:
        idx = log_text.find(marker)
        if idx >= 0:
            reply = log_text[idx + len(marker):].strip()
            if reply:
                return reply[:4000]

    lines = [line.strip() for line in log_text.splitlines() if line.strip()]
    if not lines:
        return ""
    return lines[-1][:4000]


def create_session(config: BridgeConfig) -> tuple[bool, str, str]:
    enum_name = _dialog_enum_name(config.dialog_type)
    try:
        result = execute_bsl(
            config.bridge_url,
            "РезультатВыполнения = ИИА_ДиалогCOM.СоздатьBridgeСессию("
            + bsl_string(config.user)
            + ", Перечисления.ИИА_ТипДиалога."
            + enum_name
            + ");",
            timeout=60,
        )
    except Exception as exc:
        return False, "", f"Ошибка вызова ИИА_ДиалогCOM.СоздатьBridgeСессию: {exc}"

    session_id = str(_get(result, "SessionId") or _get(result, "СсылкаДиалога") or "")
    if isinstance(_get(result, "СсылкаДиалога"), dict):
        session_id = str(_get(result, "SessionId") or _get(result, "СсылкаДиалога").get("uuid") or "")
    ok = bool(_get(result, "Успех", False)) and bool(session_id)
    return ok, session_id, "" if ok else "Bridge session не была создана"


def close_session(config: BridgeConfig, session_id: str) -> tuple[bool, str]:
    if not session_id:
        return False, "Пустой session_id"

    try:
        result = call_exported(
            config.bridge_url,
            "ИИА_ДиалогCOM",
            "ЗакрытьBridgeСессию",
            bsl_string(session_id),
            timeout=60,
        )
    except Exception as exc:
        return False, f"Ошибка вызова ИИА_ДиалогCOM.ЗакрытьBridgeСессию: {exc}"

    return bool(_get(result, "Успех", False)), str(_get(result, "Сообщение") or "")


def _dialog_ref_str(value, fallback: str = "") -> str:
    if isinstance(value, dict):
        return str(value.get("uuid") or value.get("presentation") or fallback)
    return str(value or fallback)


def run_bridge_turn(
    request: BridgeRequest,
    config: BridgeConfig,
    session_id: str,
) -> BridgeResponse:
    prompt_text = build_prompt(request, config)
    try:
        result = execute_bsl(
            config.bridge_url,
            "РезультатВыполнения = ИИА_ДиалогCOM.ВыполнитьХодBridge("
            + bsl_string(session_id)
            + ", "
            + bsl_string(prompt_text)
            + ");",
            timeout=280,
        )
    except Exception as exc:
        return BridgeResponse(
            ok=False,
            task_id=request.task_id,
            user_message=request.user_message,
            prompt_text=prompt_text,
            agent_success=False,
            agent_reply="",
            dialog_ref=session_id,
            usage_tokens=0,
            log_excerpt="",
            session_id=session_id,
            error=f"Ошибка вызова ИИА_ДиалогCOM.ВыполнитьХодBridge: {exc}",
        )

    success = bool(_get(result, "Успех", False))
    log_text = str(_get(result, "Лог") or "")
    reply = str(_get(result, "ОтветАссистента") or "")
    if not reply:
        reply = _extract_agent_reply(log_text)

    return BridgeResponse(
        ok=True,
        task_id=request.task_id,
        user_message=request.user_message,
        prompt_text=prompt_text,
        agent_success=success,
        agent_reply=reply,
        dialog_ref=_dialog_ref_str(_get(result, "СсылкаДиалога"), session_id),
        usage_tokens=int(_get(result, "UsageTokens") or 0),
        log_excerpt=log_text[: config.max_log_chars],
        session_id=str(_get(result, "SessionId") or session_id),
        error="",
    )


def run_bridge(request: BridgeRequest, config: BridgeConfig) -> BridgeResponse:
    from automation.bridge.client import run_agent_dialog

    prompt_text = build_prompt(request, config)
    try:
        result = run_agent_dialog(
            config.bridge_url,
            config.user,
            prompt_text,
            config.dialog_type,
            auto_confirm=True,
        )
    except Exception as exc:
        return BridgeResponse(
            ok=False,
            task_id=request.task_id,
            user_message=request.user_message,
            prompt_text=prompt_text,
            agent_success=False,
            agent_reply="",
            dialog_ref="",
            usage_tokens=0,
            log_excerpt="",
            session_id="",
            error=f"Ошибка вызова ИИА_ДиалогCOM: {exc}",
        )

    success = bool(_get(result, "Успех", False))
    log_text = str(_get(result, "Лог") or "")
    dialog_ref = _dialog_ref_str(_get(result, "СсылкаДиалога") or result.get("dialog_uuid"))
    usage_tokens = int(_get(result, "UsageTokens") or 0)
    agent_reply = _extract_agent_reply(log_text)

    return BridgeResponse(
        ok=True,
        task_id=request.task_id,
        user_message=request.user_message,
        prompt_text=prompt_text,
        agent_success=success,
        agent_reply=agent_reply,
        dialog_ref=dialog_ref,
        usage_tokens=usage_tokens,
        log_excerpt=log_text[: config.max_log_chars],
        session_id=dialog_ref,
        error="",
    )


def main() -> int:
    setup_console_encoding()

    parser = argparse.ArgumentParser(description="Scaffold bridge между benchmark runner и 1С-агентом")
    parser.add_argument("--config", default=None, help="Путь к JSON-конфигу bridge")
    parser.add_argument("--request", default=None, help="Путь к JSON-запросу benchmark runner")
    parser.add_argument("--history", default=None, help="Путь к JSON-истории сообщений")
    parser.add_argument("--text", default=None, help="Последнее сообщение пользователя")
    parser.add_argument("--task-id", default="adhoc_task", help="Идентификатор задачи")
    parser.add_argument("--bridge-url", default=None, help="URL HTTP-сервиса Codex Test Bridge")
    parser.add_argument("--output", default=None, help="Путь к JSON-ответу")
    parser.add_argument("--session-id", default=None, help="ID существующей bridge-сессии")
    parser.add_argument("--create-session", action="store_true", help="Создать bridge-сессию и вернуть session_id")
    parser.add_argument("--close-session", default=None, help="Закрыть bridge-сессию по session_id")
    args = parser.parse_args()

    config = load_bridge_config(args.config, args.bridge_url)
    if args.create_session:
        ok, session_id, error = create_session(config)
        payload = {"ok": ok, "session_id": session_id, "error": error}
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    if args.close_session:
        ok, message = close_session(config, args.close_session)
        payload = {"ok": ok, "session_id": args.close_session, "message": message}
        if args.output:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
        else:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if ok else 1

    request = load_request(args.request, args.text, args.task_id, args.history)
    if config.use_sessions and args.session_id:
        response = run_bridge_turn(request, config, args.session_id)
    else:
        response = run_bridge(request, config)

    payload = asdict(response)
    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return 0 if response.ok else 1


if __name__ == "__main__":
    sys.exit(main())
