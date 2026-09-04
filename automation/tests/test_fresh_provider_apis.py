"""Contract tests for direct providers supported by the 1C:Fresh edition.

Live tests are enabled only when provider credentials are present:
  GIGACHAT_AUTH_KEY
  YANDEX_AI_API_KEY and YANDEX_AI_FOLDER_ID
"""

from __future__ import annotations

import base64
import json
import os
import ssl
import unittest
import urllib.error
import urllib.parse
import urllib.request
import uuid


def ssl_context() -> ssl.SSLContext | None:
    verify = os.getenv("GIGACHAT_VERIFY_SSL_CERTS", "true").lower()
    return ssl._create_unverified_context() if verify in {"0", "false", "no"} else None


def post_json(url: str, headers: dict[str, str], body: dict) -> dict:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=90, context=ssl_context()) as response:
        return json.loads(response.read().decode("utf-8"))


def gigachat_token(key: str) -> str:
    scopes = ("GIGACHAT_API_PERS", "GIGACHAT_API_B2B", "GIGACHAT_API_CORP")
    encoded = key if ":" not in key else base64.b64encode(key.encode()).decode()
    for scope in scopes:
        request = urllib.request.Request(
            "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
            data=urllib.parse.urlencode({"scope": scope}).encode(),
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
                "RqUID": str(uuid.uuid4()),
                "Authorization": f"Basic {encoded}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30, context=ssl_context()) as response:
                return json.loads(response.read().decode("utf-8"))["access_token"]
        except urllib.error.HTTPError:
            continue
    raise AssertionError("GigaChat OAuth failed for PERS, B2B and CORP scopes")


TOOL_PARAMETERS = {
    "type": "object",
    "properties": {"value": {"type": "integer"}},
    "required": ["value"],
    "additionalProperties": False,
}


class FreshProviderLiveTests(unittest.TestCase):
    def test_gigachat_required_function_call(self) -> None:
        key = os.getenv("GIGACHAT_AUTH_KEY", "")
        if not key:
            self.skipTest("GIGACHAT_AUTH_KEY is not configured")
        token = gigachat_token(key)
        data = post_json(
            "https://api.giga.chat/v1/chat/completions",
            {"Authorization": f"Bearer {token}"},
            {
                "model": os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro"),
                "messages": [{"role": "user", "content": "Передай число 7 в функцию."}],
                "functions": [{"name": "submit_value", "description": "Возвращает число", "parameters": TOOL_PARAMETERS}],
                "function_call": {"name": "submit_value"},
                "temperature": 0,
                "max_tokens": 256,
            },
        )
        call = data["choices"][0]["message"]["function_call"]
        self.assertEqual(call["name"], "submit_value")
        args = call["arguments"]
        if isinstance(args, str):
            args = json.loads(args)
        self.assertEqual(args["value"], 7)

    def test_gigachat_nested_agent_plan(self) -> None:
        key = os.getenv("GIGACHAT_AUTH_KEY", "")
        if not key:
            self.skipTest("GIGACHAT_AUTH_KEY is not configured")
        token = gigachat_token(key)
        schema = {
            "type": "object",
            "properties": {
                "goal": {"type": "string"},
                "steps": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "action": {"type": "string", "enum": ["read", "write"]},
                        },
                        "required": ["id", "action"],
                        "additionalProperties": False,
                    },
                },
            },
            "required": ["goal", "steps"],
            "additionalProperties": False,
        }
        data = post_json(
            "https://api.giga.chat/v1/chat/completions",
            {"Authorization": f"Bearer {token}"},
            {
                "model": os.getenv("GIGACHAT_MODEL", "GigaChat-2-Pro"),
                "messages": [{"role": "user", "content": "Создай план: сначала чтение, затем запись."}],
                "functions": [{"name": "submit_plan", "description": "Фиксирует план агента", "parameters": schema}],
                "function_call": {"name": "submit_plan"},
                "temperature": 0,
                "max_tokens": 512,
            },
        )
        call = data["choices"][0]["message"]["function_call"]
        args = call["arguments"]
        if isinstance(args, str):
            args = json.loads(args)
        self.assertEqual(call["name"], "submit_plan")
        self.assertGreaterEqual(len(args["steps"]), 2)
        self.assertEqual(args["steps"][0]["action"], "read")
        self.assertEqual(args["steps"][1]["action"], "write")

    def test_yandex_required_tool_call(self) -> None:
        key = os.getenv("YANDEX_AI_API_KEY", "")
        folder = os.getenv("YANDEX_AI_FOLDER_ID", "")
        if not key or not folder:
            self.skipTest("YANDEX_AI_API_KEY/YANDEX_AI_FOLDER_ID are not configured")
        data = post_json(
            "https://ai.api.cloud.yandex.net/v1/chat/completions",
            {"Authorization": f"Api-Key {key}"},
            {
                "model": os.getenv("YANDEX_AI_MODEL", f"gpt://{folder}/yandexgpt/latest"),
                "messages": [{"role": "user", "content": "Передай число 7 в инструмент."}],
                "tools": [{"type": "function", "function": {"name": "submit_value", "description": "Возвращает число", "parameters": TOOL_PARAMETERS}}],
                "tool_choice": {"type": "function", "function": {"name": "submit_value"}},
                "temperature": 0,
                "max_tokens": 256,
            },
        )
        call = data["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "submit_value")
        self.assertEqual(json.loads(call["function"]["arguments"])["value"], 7)

    def test_yandex_agent_plan_fits_provider_token_budget(self) -> None:
        key = os.getenv("YANDEX_AI_API_KEY", "")
        folder = os.getenv("YANDEX_AI_FOLDER_ID", "")
        if not key or not folder:
            self.skipTest("YANDEX_AI_API_KEY/YANDEX_AI_FOLDER_ID are not configured")
        step = {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "kind": {"type": "string"},
                "title": {"type": "string"},
                "depends_on": {"type": "array", "items": {"type": "string"}},
                "input": {"type": "object", "additionalProperties": True},
            },
            "required": ["id", "kind", "title", "depends_on", "input"],
            "additionalProperties": False,
        }
        schema = {
            "type": "object",
            "properties": {
                "plan_version": {"type": "integer"},
                "goal": {"type": "string"},
                "steps": {"type": "array", "items": step},
            },
            "required": ["plan_version", "goal", "steps"],
            "additionalProperties": False,
        }
        long_context = " ".join(
            [
                "Сначала уточни метаданные и поля объекта.",
                "Затем сформируй безопасный запрос 1С без неподставленных параметров.",
                "После выполнения покажи пользователю проверенный результат.",
            ]
            * 30
        )
        data = post_json(
            "https://ai.api.cloud.yandex.net/v1/chat/completions",
            {"Authorization": f"Api-Key {key}"},
            {
                "model": os.getenv("YANDEX_AI_MODEL", f"gpt://{folder}/yandexgpt/latest"),
                "messages": [
                    {"role": "system", "content": "Верни typed-plan только через submit_plan."},
                    {"role": "user", "content": long_context},
                ],
                "tools": [{"type": "function", "function": {"name": "submit_plan", "description": "Возвращает typed-plan агента", "parameters": schema}}],
                "tool_choice": "required",
                "temperature": 0,
                "max_tokens": 4096,
            },
        )
        choice = data["choices"][0]
        self.assertEqual(choice["finish_reason"], "tool_calls")
        call = choice["message"]["tool_calls"][0]
        self.assertEqual(call["function"]["name"], "submit_plan")
        plan = json.loads(call["function"]["arguments"])
        self.assertGreaterEqual(len(plan["steps"]), 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
