# -*- coding: utf-8 -*-
"""UI lifecycle E2E for user skills: paste JSON, save, test, export/import."""

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

from automation.ui.web_agent_skill_e2e import bsl_string, click_label, close_font_dialog, replace_focused_text
from automation.ui.web_agent_skill_write_e2e import bridge_execute, cleanup_skill
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding
from automation.ui.web_skills_negative_ui import focus_textarea, read_textarea


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'


def make_skill_json(skill_name: str, marker: str) -> str:
    return json.dumps(
        {
            "name": skill_name,
            "title": "UI lifecycle skill",
            "description": "Проверка UI сохранения переносимого JSON skill.",
            "enabled": True,
            "owner": "user",
            "scope": "user",
            "triggers": [marker, "ui lifecycle skill"],
            "dialog_types": ["Агент"],
            "target_object_type": "Document",
            "target_object_name": "ЗаказПокупателя",
            "prompt": marker + ": используй переносимый JSON skill для заказа покупателя.",
            "risk_level": "write",
            "enforcement": "warn",
            "approval_required": True,
            "template_vars": {"comment": {"type": "string", "required": True, "source": "user_prompt"}},
            "dsl_template_mode": "strict",
            "dsl_template": {
                "dsl_version": 2,
                "steps": [
                    {"action": "CreateDocument", "object_name": "ЗаказПокупателя", "data": {"Комментарий": "$comment"}},
                    {"action": "Write"},
                ],
            },
            "policy": {
                "risk_level": "write",
                "enforcement": "warn",
                "approval_required": True,
                "allowed_actions": ["CreateDocument", "SetField", "Write", "ShowInfo"],
                "forbidden_actions": ["DeleteObject", "PostDocument"],
                "required_checks": ["approval_before_write"],
            },
        },
        ensure_ascii=False,
        indent=2,
    )


def inspect_skill(bridge_url: str, skill_name: str, marker: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура;"
        "Скил = ИИА_Skills.ПолучитьСкил(" + bsl_string(skill_name) + ");"
        "РезультатВыполнения.Вставить(\"exists\", Скил <> Неопределено);"
        "Если Скил <> Неопределено Тогда "
        "РезультатВыполнения.Вставить(\"enabled\", Скил.enabled);"
        "РезультатВыполнения.Вставить(\"owner\", ?(Скил.Свойство(\"owner\"), Скил.owner, \"\"));"
        "РезультатВыполнения.Вставить(\"target\", ?(Скил.Свойство(\"target_object_name\"), Скил.target_object_name, \"\"));"
        "РезультатВыполнения.Вставить(\"hasTemplate\", Скил.Свойство(\"dsl_template_json\") И СтрНайти(Скил.dsl_template_json, \"CreateDocument\") > 0);"
        "КонецЕсли;"
        "Скилы = ИИА_Skills.ПодобратьСкилы(" + bsl_string(marker + ' создай заказ') + ", Перечисления.ИИА_ТипДиалога.Агент, , 5);"
        "РезультатВыполнения.Вставить(\"matched\", СтрНайти(ИИА_Skills.ПолучитьИменаСкиловСтрокой(Скилы), " + bsl_string(skill_name) + ") > 0);"
    )
    return bridge_execute(bridge_url, code)


def export_skill_json(bridge_url: str, skill_name: str) -> str:
    code = (
        "Карточка = ИИА_Skills.ПолучитьКарточкуСкила(" + bsl_string(skill_name) + ");"
        "Если Карточка = Неопределено Тогда "
        "РезультатВыполнения = \"\";"
        "Иначе "
        "РезультатВыполнения = ИИА_Skills.КарточкаВJSON(Карточка);"
        "КонецЕсли;"
    )
    result = bridge_execute(bridge_url, code)
    return str(result or "")


def visible_textarea_contains(test: BrowserQuery1CTest, needle: str) -> bool:
    script = r"""
((needle)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 return Array.from(document.querySelectorAll('textarea')).filter(visible).some(e=>(e.value||'').includes(needle));
})(""" + json.dumps(needle, ensure_ascii=False) + """)
"""
    raw = test._evaluate(script)
    return raw is True or str(raw).lower() == "true"


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    suffix = time.strftime("%Y%m%d%H%M%S")
    skill_name = args.skill_name
    marker = "E2E_UI_SKILL_LIFECYCLE_" + suffix
    skill_json = make_skill_json(skill_name, marker)
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
        log_file=str(artifact_dir / "web_skills_lifecycle_e2e.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    result: dict[str, object] = {"skillName": skill_name, "marker": marker}
    try:
        cleanup_skill(args.bridge_url, skill_name)
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()
        command = urllib.parse.quote("CommonCommand.ИИА_Skills", safe=".")
        skills_url = args.web_url.rstrip("/") + "/#e1cib/command/" + command
        test._session_call("Page.navigate", {"url": skills_url})
        test._wait_until_text_contains("Skills", args.timeout_sec)

        result["jsonFocus"] = focus_textarea(test, 1)
        replace_focused_text(test, skill_json)
        result["saveClick"] = click_label(test, "Сохранить")
        time.sleep(2)
        result["afterSave"] = inspect_skill(args.bridge_url, skill_name, marker)
        result["textareaHasNameAfterSave"] = visible_textarea_contains(test, skill_name)
        exported_json = export_skill_json(args.bridge_url, skill_name)
        result["exportedHasName"] = skill_name in exported_json

        result["testRequestFocus"] = focus_textarea(test, 2)
        replace_focused_text(test, marker + " создай заказ покупателя")
        result["runTestClick"] = click_label(test, "Запустить тест")
        time.sleep(2)
        body = test._safe_body_text()
        result["runTestMentionsSkill"] = skill_name in body or marker in body
        result["runTestMentionsTemplate"] = "dsl_template" in body or "DSL" in body

        cleanup_skill(args.bridge_url, skill_name)
        result["afterDelete"] = inspect_skill(args.bridge_url, skill_name, marker)

        result["jsonRefocus"] = focus_textarea(test, 1)
        replace_focused_text(test, exported_json)
        result["resaveClick"] = click_label(test, "Сохранить")
        time.sleep(2)
        result["afterReimport"] = inspect_skill(args.bridge_url, skill_name, marker)

        (artifact_dir / "web_skills_lifecycle_e2e_body.txt").write_text(body, encoding="utf-8")
        required = {
            "savedExists": bool(result["afterSave"].get("exists")),
            "savedMatched": bool(result["afterSave"].get("matched")),
            "savedHasTemplate": bool(result["afterSave"].get("hasTemplate")),
            "textareaHasNameAfterSave": bool(result.get("textareaHasNameAfterSave")),
            "runTestMentionsSkill": bool(result.get("runTestMentionsSkill")),
            "runTestMentionsTemplate": bool(result.get("runTestMentionsTemplate")),
            "exportedHasName": bool(result.get("exportedHasName")),
            "deletedMissing": not bool(result["afterDelete"].get("exists")),
            "reimportExists": bool(result["afterReimport"].get("exists")),
            "reimportMatched": bool(result["afterReimport"].get("matched")),
        }
        result["required"] = required
        result["success"] = all(required.values())
        return result
    finally:
        test._close()
        cleanup_skill(args.bridge_url, skill_name)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UI lifecycle E2E for AI Skills form")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--skill-name", default="user-skill-ui-lifecycle-e2e")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "web_skills_artifacts"))
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_skills_lifecycle_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
