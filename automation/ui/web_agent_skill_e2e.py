# -*- coding: utf-8 -*-
"""Reusable E2E test: ordinary AI Agent form selects a user skill."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'


def bsl_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def bridge_execute(bridge_url: str, code: str, timeout_sec: int = 90) -> dict:
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


def make_skill_json(skill_name: str, marker: str) -> str:
    return json.dumps(
        {
            "name": skill_name,
            "title": "E2E обычный агент skill",
            "description": "Fixture skill for ordinary agent UI e2e.",
            "enabled": True,
            "owner": "user",
            "scope": "user",
            "triggers": [marker, "e2e agent skill", "заказ клиента"],
            "dialog_types": ["Агент"],
            "target_object_type": "Document",
            "target_object_name": "ЗаказПокупателя",
            "prompt": (
                marker
                + ": для запросов на создание заказа клиента сначала проверь метаданные "
                "Документ.ЗаказПокупателя через GetMetadata/GetObjectFields, подготовь поля "
                "и не выполняй Write без подтверждения пользователя."
            ),
            "risk_level": "write",
            "enforcement": "warn",
            "approval_required": True,
            "workflow": [],
            "template_vars": {
                "customer": {"type": "CatalogRef.Контрагенты", "required": True, "source": "user_prompt"},
                "items": {"type": "array", "required": True, "source": "user_prompt"},
                "target_object": {"type": "Document.ЗаказПокупателя", "required": True, "source": "skill"},
            },
            "dsl_template_mode": "validate",
            "dsl_template": {
                "dsl_version": 1,
                "steps": [
                    {"action": "GetMetadata", "object": "Document.ЗаказПокупателя", "save_as": "metadata"},
                    {"action": "FindReferenceByName", "object": "Catalog.Контрагенты", "value": "$customer", "save_as": "customer_ref"},
                    {"action": "CreateDocument", "object": "ЗаказПокупателя", "save_as": "document_ref"},
                    {"action": "SetField", "target": "$document_ref", "field": "Контрагент", "value": "$customer_ref"},
                    {"action": "ShowInfo", "value": "Предварительный результат подготовлен."},
                ],
            },
            "policy": {
                "risk_level": "write",
                "enforcement": "warn",
                "approval_required": True,
                "allowed_actions": ["GetMetadata", "GetObjectFields", "FindReferenceByName", "CreateDocument", "SetField", "Write", "ShowInfo"],
                "forbidden_actions": ["DeleteObject"],
                "required_checks": ["metadata_before_write", "approval_before_write"],
            },
        },
        ensure_ascii=False,
    )


def install_fixture_skill(bridge_url: str, skill_name: str, marker: str) -> None:
    skill_json = make_skill_json(skill_name, marker)
    code = (
        "ИИА_Skills.УдалитьПользовательскийСкил(" + bsl_string(skill_name) + ");"
        "Карточка = ИИА_Skills.КарточкаИзJSON(" + bsl_string(skill_json) + ");"
        "ИИА_Skills.СохранитьПользовательскийСкил(Карточка);"
        "РезультатВыполнения = Новый Структура(\"ok,name\", Истина, " + bsl_string(skill_name) + ");"
    )
    bridge_execute(bridge_url, code)


def cleanup_fixture(bridge_url: str, skill_name: str, marker: str) -> None:
    code = (
        "РезультатВыполнения = Новый Структура(\"deleted,stopped\", Ложь, Ложь);"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 20 Диалоги.Ссылка КАК Ссылка ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.ТипДиалога = &ТипДиалога УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.Агент);"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Пока Выборка.Следующий() Цикл "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект();"
        "Для Каждого Сообщение Из Диалог.Сообщения Цикл "
        "Если СтрНайти(Строка(Сообщение.Текст), " + bsl_string(marker) + ") > 0 Тогда "
        "Попытка ИИА_ВызовСервера.ОркестраторОстановить(Выборка.Ссылка); РезультатВыполнения.stopped = Истина; Исключение КонецПопытки;"
        "Прервать; КонецЕсли; КонецЦикла; КонецЦикла;"
        "Попытка ИИА_Skills.УдалитьПользовательскийСкил(" + bsl_string(skill_name) + "); РезультатВыполнения.deleted = Истина; Исключение КонецПопытки;"
    )
    try:
        bridge_execute(bridge_url, code)
    except Exception:
        pass


def close_font_dialog() -> bool:
    try:
        from pywinauto import Desktop
    except Exception:
        return False
    deadline = time.time() + 10
    while time.time() < deadline:
        for window in Desktop(backend="uia").windows(title_re=".*1С.*"):
            try:
                window.set_focus()
            except Exception:
                pass
            for button in window.descendants(control_type="Button"):
                text = (button.window_text() or "").strip()
                if text in ("ОК", "OK") or text.upper() == "OK":
                    try:
                        button.invoke()
                        time.sleep(1)
                        return True
                    except Exception:
                        pass
        time.sleep(0.5)
    return False


def click_label(test: BrowserQuery1CTest, label: str) -> str:
    script = r"""
((label)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>4&&r.height>4&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const fire=e=>{
  e.scrollIntoView({block:'center', inline:'center'});
  ['pointerdown','mousedown','mouseup','click'].forEach(type=>e.dispatchEvent(new MouseEvent(type,{bubbles:true,cancelable:true,view:window,buttons:1})));
 };
 const walker=document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
 let node;
 while(node=walker.nextNode()) {
  if(!(node.nodeValue||'').includes(label)) continue;
  let e=node.parentElement;
  while(e && e!==document.body && !/^(A|BUTTON)$/i.test(e.tagName) && e.getAttribute('role')!=='button') e=e.parentElement;
  if(e && visible(e)) { fire(e); return 'clicked:textnode'; }
 }
 let candidates=Array.from(document.querySelectorAll('*')).filter(e=>visible(e)&&(e.innerText||e.getAttribute('aria-label')||e.getAttribute('title')||e.value||'').trim()===label)
  .map(e=>{const r=e.getBoundingClientRect();return {e:e, area:r.width*r.height};}).sort((a,b)=>a.area-b.area);
 if(!candidates.length) {
  candidates=Array.from(document.querySelectorAll('button, a, div, span, input')).filter(e=>visible(e)&&(e.innerText||e.getAttribute('aria-label')||e.getAttribute('title')||e.value||'').includes(label))
   .map(e=>{const r=e.getBoundingClientRect();return {e:e, area:r.width*r.height};}).sort((a,b)=>a.area-b.area);
 }
 if(!candidates.length) return 'missing';
 fire(candidates[0].e);
 return 'clicked';
})(""" + json.dumps(label, ensure_ascii=False) + """)
"""
    return test._evaluate(script)


def focus_prompt(test: BrowserQuery1CTest) -> str:
    script = r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 let items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 if(!items.length) {
  items=Array.from(document.querySelectorAll('input')).filter(visible)
   .filter(e=>!(e.className||'').includes('captionbar'))
   .sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 }
 if(!items.length) return 'missing';
 const e=items[0]; e.scrollIntoView({block:'center'}); e.focus(); e.click(); return e.tagName;
})()
"""
    return test._evaluate(script)


def replace_focused_text(test: BrowserQuery1CTest, text: str) -> None:
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 17, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 65, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 65, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 17})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 8})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 8})
    test._session_call("Input.insertText", {"text": text})


def inspect_dialog(bridge_url: str, marker: str, skill_name: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура;"
        "РезультатВыполнения.Вставить(\"found\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasUserPrompt\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasSkillName\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasSkillMarker\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasActiveSkills\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasTarget\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasDslTemplate\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasTemplateVars\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasTemplateMode\", Ложь);"
        "РезультатВыполнения.Вставить(\"dslGetMetadata\", Ложь);"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 30 Диалоги.Ссылка КАК Ссылка, Диалоги.ДатаСоздания КАК ДатаСоздания "
        "ИЗ Справочник.ИИА_Диалоги КАК Диалоги ГДЕ Диалоги.ТипДиалога = &ТипДиалога УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.Агент);"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Пока Выборка.Следующий() Цикл "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект(); Найден = Ложь;"
        "Для Каждого Сообщение Из Диалог.Сообщения Цикл "
        "Если СтрНайти(Строка(Сообщение.Текст), " + bsl_string(marker) + ") > 0 Тогда Найден = Истина; Прервать; КонецЕсли; КонецЦикла;"
        "Если Найден Тогда "
        "Лог = ИИА_Сервер.ПолучитьЛогДиалога(Выборка.Ссылка);"
        "РезультатВыполнения.found = Истина;"
        "РезультатВыполнения.Вставить(\"dialog\", Строка(Выборка.Ссылка));"
        "РезультатВыполнения.logHasUserPrompt = СтрНайти(Лог, " + bsl_string(marker) + ") > 0;"
        "РезультатВыполнения.logHasSkillName = СтрНайти(Лог, " + bsl_string(skill_name) + ") > 0;"
        "РезультатВыполнения.logHasSkillMarker = СтрНайти(Лог, \"E2E_MARKER_NORMAL_AGENT_SKILL\") > 0;"
        "РезультатВыполнения.logHasActiveSkills = СтрНайти(Лог, \"АКТИВНЫЕ SKILLS\") > 0;"
        "РезультатВыполнения.logHasTarget = СтрНайти(Лог, \"target_object_name=ЗаказПокупателя\") > 0;"
        "РезультатВыполнения.logHasDslTemplate = СтрНайти(Лог, \"DSL_TEMPLATE_JSON\") > 0;"
        "РезультатВыполнения.logHasTemplateVars = СтрНайти(Лог, \"TEMPLATE_VARS_JSON\") > 0;"
        "РезультатВыполнения.logHasTemplateMode = СтрНайти(Лог, \"DSL_TEMPLATE_MODE: validate\") > 0;"
        "РезультатВыполнения.dslGetMetadata = СтрНайти(Лог, \"GetMetadata\") > 0;"
        "Позиция = СтрНайти(Лог, " + bsl_string(skill_name) + ");"
        "Если Позиция > 0 Тогда РезультатВыполнения.Вставить(\"aroundSkillName\", Сред(Лог, Макс(1, Позиция - 120), 360)); КонецЕсли;"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code)


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    marker = args.marker or ("E2E_AGENT_UI_SKILL_USE_" + time.strftime("%Y%m%d%H%M%S"))
    skill_marker = "E2E_MARKER_NORMAL_AGENT_SKILL"
    skill_name = args.skill_name
    install_fixture_skill(args.bridge_url, skill_name, skill_marker)
    result = {"marker": marker, "skillName": skill_name}
    test = None
    try:
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
            log_file=str(artifact_dir / "web_agent_skill_e2e.log"),
            artifact_dir=str(artifact_dir),
            headless=not args.headed,
            skip_com_prepare=True,
        )
        test = BrowserQuery1CTest(config, Logger(config.log_file))
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()
        command = urllib.parse.quote("CommonCommand.ИИА_Агент", safe=".")
        test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
        test._wait_until_text_contains("ИИ Агент", args.timeout_sec)
        result["newDialogClick"] = click_label(test, "Новый диалог")
        time.sleep(2)
        result["promptFocus"] = focus_prompt(test)
        prompt = marker + ": e2e agent skill создай заказ клиента для Ромашка на Кабель 10 штук. Не записывай без подтверждения."
        replace_focused_text(test, prompt)
        result["sendClick"] = click_label(test, "Отправить")
        time.sleep(args.agent_wait_sec)
        body_text = test._safe_body_text()
        result["promptVisible"] = marker in body_text
        result["bodyHead"] = body_text[:1200]
        (artifact_dir / "web_agent_skill_e2e_body.txt").write_text(body_text, encoding="utf-8")
        result.update(inspect_dialog(args.bridge_url, marker, skill_name))
        required = ["found", "logHasUserPrompt", "logHasSkillName", "logHasSkillMarker", "logHasActiveSkills", "logHasTarget", "logHasDslTemplate", "logHasTemplateVars", "logHasTemplateMode", "dslGetMetadata"]
        result["success"] = all(bool(result.get(key)) for key in required)
        result["required"] = {key: bool(result.get(key)) for key in required}
        return result
    finally:
        if test is not None:
            test._close()
        cleanup_fixture(args.bridge_url, skill_name, marker)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E2E UI test for ordinary AI Agent skill selection")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--skill-name", default="user-skill-agent-ui-e2e")
    parser.add_argument("--marker", default="")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--agent-wait-sec", type=int, default=25)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "web_skills_artifacts"))
    parser.add_argument("--headed", action="store_true", help="Show Chrome window for manual debugging. Headless is default.")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_agent_skill_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
