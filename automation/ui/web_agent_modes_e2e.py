# -*- coding: utf-8 -*-
"""Reusable E2E checks for real AI Agent runs in several UI modes."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_skill_e2e import (
    cleanup_fixture,
    click_label,
    focus_prompt,
    install_fixture_skill,
    replace_focused_text,
)
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'


def bsl_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def bridge_execute(bridge_url: str, code: str, timeout_sec: int = 120) -> dict:
    import urllib.request

    body = json.dumps({"command": "ExecuteBSL", "code": code, "params": []}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        bridge_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_sec) as response:
        payload = json.loads(response.read().decode("utf-8-sig"))
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload.get("result")


def click_first_textarea(test: BrowserQuery1CTest) -> str:
    return focus_prompt(test)


def focus_mode_field(test: BrowserQuery1CTest) -> str:
    script = r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('input')).filter(visible)
  .filter(e=>(e.value||'').includes('Агент') || (e.value||'').includes('Запрос1С'))
  .sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 if(!items.length) return 'missing';
 const e=items[0]; e.scrollIntoView({block:'center'}); e.focus(); e.click(); return e.value || 'focused';
})()
"""
    return test._evaluate(script)


def press_enter(test: BrowserQuery1CTest) -> None:
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 13})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13})


def switch_mode(test: BrowserQuery1CTest, mode: str) -> dict:
    before = focus_mode_field(test)
    replace_focused_text(test, mode)
    press_enter(test)
    time.sleep(1)
    after = test._evaluate(
        r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('input')).filter(visible).filter(e=>(e.value||'').includes('Агент') || (e.value||'').includes('Запрос1С'));
 return items.length ? items[0].value : '';
})()
"""
    )
    return {"before": before, "after": after}


def send_prompt(test: BrowserQuery1CTest, prompt: str) -> dict:
    result = {"newDialogClick": click_label(test, "Новый диалог")}
    time.sleep(2)
    result["promptFocus"] = click_first_textarea(test)
    replace_focused_text(test, prompt)
    time.sleep(1)
    result["promptVisibleBeforeSend"] = prompt in test._safe_body_text()
    result["sendClick"] = click_label(test, "Отправить")
    return result


def inspect_marker(bridge_url: str, marker: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура;"
        "РезультатВыполнения.Вставить(\"found\", Ложь);"
        "РезультатВыполнения.Вставить(\"dialogType\", \"\");"
        "РезультатВыполнения.Вставить(\"logHasPrompt\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasLLM\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasDSL\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasGetMetadata\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasRunQuery\", Ложь);"
        "РезультатВыполнения.Вставить(\"hasPendingApproval\", Ложь);"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 40 Диалоги.Ссылка КАК Ссылка, Диалоги.ТипДиалога КАК ТипДиалога "
        "ИЗ Справочник.ИИА_Диалоги КАК Диалоги УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Пока Выборка.Следующий() Цикл "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект(); Найден = Ложь;"
        "Для Каждого Сообщение Из Диалог.Сообщения Цикл "
        "Если СтрНайти(Строка(Сообщение.Текст), " + bsl_string(marker) + ") > 0 Тогда Найден = Истина; Прервать; КонецЕсли; КонецЦикла;"
        "Если Найден Тогда "
        "Лог = ИИА_Сервер.ПолучитьЛогДиалога(Выборка.Ссылка);"
        "РезультатВыполнения.found = Истина;"
        "РезультатВыполнения.dialogType = Строка(Выборка.ТипДиалога);"
        "РезультатВыполнения.Вставить(\"dialog\", Строка(Выборка.Ссылка));"
        "РезультатВыполнения.logHasPrompt = СтрНайти(Лог, " + bsl_string(marker) + ") > 0;"
        "РезультатВыполнения.logHasLLM = СтрНайти(Лог, \"LLM\") > 0 ИЛИ СтрНайти(Лог, \"Запрос к ИИ\") > 0;"
        "РезультатВыполнения.logHasDSL = СтрНайти(Лог, \"DSL\") > 0;"
        "РезультатВыполнения.logHasGetMetadata = СтрНайти(Лог, \"GetMetadata\") > 0;"
        "РезультатВыполнения.logHasRunQuery = СтрНайти(Лог, \"RunQuery\") > 0;"
        "Состояние = ИИА_ВызовСервера.ПолучитьСостояниеПодтверждения(Выборка.Ссылка);"
        "РезультатВыполнения.hasPendingApproval = Состояние <> Неопределено И Состояние.Свойство(\"status\") И ВРег(Строка(Состояние.status)) = \"PENDING\";"
        "Позиция = СтрНайти(Лог, " + bsl_string(marker) + ");"
        "Если Позиция > 0 Тогда РезультатВыполнения.Вставить(\"aroundPrompt\", Сред(Лог, Макс(1, Позиция - 120), 420)); КонецЕсли;"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code)


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    config = WebUiConfig(
        web_url=args.web_url,
        chrome_exe=args.chrome_exe,
        base_path=DEFAULT_CONNECTION_STRING,
        user=args.user,
        password=args.password,
        query_text="",
        query_params_json="",
        expected_text="",
        timeout_sec=args.timeout_sec,
        log_file=str(artifact_dir / "web_agent_modes_e2e.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    skill_name = "user-skill-agent-modes-e2e"
    install_fixture_skill(args.bridge_url, skill_name, "E2E_AGENT_MODES_WRITE_SKILL")
    result: dict[str, object] = {"scenarios": []}
    try:
        test._launch_browser()
        test._open_initial_target()
        command = urllib.parse.quote("CommonCommand.ИИА_Агент", safe=".")
        scenarios = [
            {
                "name": "agent_metadata",
                "mode": "Агент",
                "marker": "E2E_AGENT_MODE_METADATA_" + time.strftime("%Y%m%d%H%M%S"),
                "prompt": "проверь через метаданные, существует ли документ ЗаказПокупателя, ничего не записывай",
                "required": ["found", "logHasPrompt", "logHasLLM", "logHasDSL", "logHasGetMetadata"],
            },
            {
                "name": "query1c_runquery",
                "mode": "Запрос1С",
                "marker": "E2E_AGENT_MODE_QUERY1C_" + time.strftime("%Y%m%d%H%M%S"),
                "prompt": "выполни безопасный запрос: ВЫБРАТЬ ПЕРВЫЕ 1 Наименование ИЗ Справочник.Контрагенты",
                "required": ["found", "logHasPrompt", "logHasDSL", "logHasRunQuery"],
            },
            {
                "name": "agent_write_approval",
                "mode": "Агент",
                "marker": "E2E_AGENT_MODE_APPROVAL_" + time.strftime("%Y%m%d%H%M%S"),
                "prompt": "E2E_AGENT_MODES_WRITE_SKILL создай заказ клиента для Ромашка на Кабель 1 штука. Не записывай без подтверждения.",
                "required": ["found", "logHasPrompt", "logHasDSL", "logHasGetMetadata"],
            },
        ]
        for scenario in scenarios:
            test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
            test._wait_until_text_contains("ИИ Агент", args.timeout_sec)
            time.sleep(2)
            scenario_result = {"name": scenario["name"], "mode": scenario["mode"], "marker": scenario["marker"]}
            if scenario["mode"] == "Агент":
                scenario_result["modeSwitch"] = {"skipped": True}
            else:
                scenario_result["modeSwitch"] = switch_mode(test, scenario["mode"])
            full_prompt = scenario["marker"] + ": " + scenario["prompt"]
            scenario_result.update(send_prompt(test, full_prompt))
            time.sleep(args.agent_wait_sec)
            scenario_result.update(inspect_marker(args.bridge_url, scenario["marker"]))
            scenario_result["required"] = {key: bool(scenario_result.get(key)) for key in scenario["required"]}
            scenario_result["success"] = all(scenario_result["required"].values())
            result["scenarios"].append(scenario_result)
        result["success"] = all(item.get("success") for item in result["scenarios"])
        return result
    finally:
        test._close()
        cleanup_fixture(args.bridge_url, skill_name, "E2E_AGENT_MODES")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Real AI Agent UI E2E scenarios for multiple modes")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--timeout-sec", type=int, default=70)
    parser.add_argument("--agent-wait-sec", type=int, default=35)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "agent_ui_audit"))
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_agent_modes_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
