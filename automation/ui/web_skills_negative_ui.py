# -*- coding: utf-8 -*-
"""Reusable negative UI checks for the AI Skills form."""

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

from automation.ui.web_agent_skill_e2e import click_label, close_font_dialog, replace_focused_text
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'


def focus_textarea(test: BrowserQuery1CTest, index: int) -> str:
    script = r"""
((index)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 if(index<0 || index>=items.length) return 'missing:' + items.length;
 const e=items[index]; e.scrollIntoView({block:'center'}); e.focus(); e.click(); return 'focused:' + index + ':' + items.length;
})(""" + str(index) + """)
"""
    return test._evaluate(script)


def read_textarea(test: BrowserQuery1CTest, index: int) -> str:
    script = r"""
((index)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 if(index<0 || index>=items.length) return '';
 return items[index].value || '';
})(""" + str(index) + """)
"""
    return test._evaluate(script)


def body_contains_any(body: str, needles: list[str]) -> bool:
    lower = body.lower()
    return any(needle.lower() in lower for needle in needles)


def close_ok_dialog(test: BrowserQuery1CTest) -> str:
    for label in ("OK", "ОК"):
        clicked = click_label(test, label)
        if clicked != "missing":
            time.sleep(1)
            return clicked
    return "missing"


def click_label_by_mouse(test: BrowserQuery1CTest, label: str, rightmost: bool = False) -> str:
    script = r"""
((label,rightmost)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>4&&r.height>4&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const candidates=Array.from(document.querySelectorAll('*')).filter(e=>visible(e)&&(e.innerText||e.getAttribute('aria-label')||e.getAttribute('title')||e.value||'').trim()===label)
  .map(e=>{const r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2,w:r.width,h:r.height,tag:e.tagName,role:e.getAttribute('role')||'',text:(e.innerText||e.value||'').trim()};})
  .sort((a,b)=>rightmost ? b.x-a.x : (a.w*a.h)-(b.w*b.h));
 if(!candidates.length) return JSON.stringify({status:'missing'});
 return JSON.stringify({status:'found', target:candidates[0]});
})(""" + json.dumps(label, ensure_ascii=False) + "," + ("true" if rightmost else "false") + """)
"""
    raw = test._evaluate(script)
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return "bad-json:" + raw[:100]
    if data.get("status") != "found":
        return data.get("status", "missing")
    target = data["target"]
    x = float(target["x"])
    y = float(target["y"])
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    test._session_call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
    return "clicked:" + target.get("tag", "")


def wait_for_textarea_contains(test: BrowserQuery1CTest, index: int, needle: str, timeout_sec: int = 8) -> str:
    deadline = time.time() + timeout_sec
    last_value = ""
    while time.time() < deadline:
        last_value = read_textarea(test, index)
        if needle in last_value:
            return last_value
        time.sleep(0.5)
    return last_value


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
        log_file=str(artifact_dir / "web_skills_negative_ui.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    result: dict[str, object] = {}
    try:
        test._launch_browser()
        test._open_initial_target()
        test._login()
        result["fontDialogClosed"] = close_font_dialog()
        command = urllib.parse.quote("CommonCommand.ИИА_Skills", safe=".")
        skills_url = args.web_url.rstrip("/") + "/#e1cib/command/" + command
        test._session_call("Page.navigate", {"url": skills_url})
        test._wait_until_text_contains("Skills", args.timeout_sec)

        result["emptyDescriptionFocus"] = focus_textarea(test, 0)
        replace_focused_text(test, "")
        result["emptyDescriptionClick"] = click_label(test, "Сгенерировать JSON")
        time.sleep(2)
        body = test._safe_body_text()
        result["emptyDescriptionWarning"] = body_contains_any(body, ["Опишите задачу для генерации skill", "Опишите задачу"])
        result["emptyDescriptionOk"] = close_ok_dialog(test)

        result["invalidJsonFocus"] = focus_textarea(test, 1)
        replace_focused_text(test, "{ bad json")
        result["invalidJsonClick"] = click_label(test, "Запустить тест")
        time.sleep(2)
        body = test._safe_body_text()
        result["invalidJsonWarning"] = body_contains_any(body, ["Некорректный JSON skill", "Ошибка чтения JSON", "JSON"])
        result["invalidJsonOk"] = close_ok_dialog(test)

        test._session_call("Page.navigate", {"url": skills_url})
        test._wait_until_text_contains("Skills", args.timeout_sec)
        time.sleep(1)
        result["selectSystemSkillClick"] = click_label(test, "Поиск метаданных")
        time.sleep(1)
        result["newSkillClick"] = click_label_by_mouse(test, "Новый")
        new_skill_json = wait_for_textarea_contains(test, 1, '"name": "user-skill-', 8)
        try:
            new_skill = json.loads(new_skill_json)
        except json.JSONDecodeError:
            new_skill = {}
        result["newSkillHasUserName"] = str(new_skill.get("name", "")).startswith("user-skill-")
        result["newSkillNotSystem"] = new_skill.get("owner") != "system"
        result["newSkillDisabled"] = new_skill.get("enabled") is False
        result["newSkillJsonEditable"] = '"workflow"' in new_skill_json and '"policy"' in new_skill_json

        test._session_call("Page.navigate", {"url": skills_url})
        test._wait_until_text_contains("Skills", args.timeout_sec)
        time.sleep(1)
        result["generateTemplateFocus"] = focus_textarea(test, 0)
        replace_focused_text(
            test,
            "Создать skill для документа ЗаказПокупателя: находить контрагента и номенклатуру, заполнять заказ клиента, не записывать без подтверждения.",
        )
        result["generateTemplateClick"] = click_label(test, "Сгенерировать JSON")
        time.sleep(3)
        generated_json = read_textarea(test, 1)
        result["generatedHasTemplateVars"] = '"template_vars"' in generated_json
        result["generatedHasDslTemplate"] = '"dsl_template"' in generated_json
        result["generatedHasTemplateMode"] = '"dsl_template_mode"' in generated_json
        result["generatedHasDocumentTarget"] = "ЗаказПокупателя" in generated_json
        result["generatedKeepsApprovalForDoNotWriteWithoutApproval"] = '"approval_required": true' in generated_json
        result["generatedTestFocus"] = focus_textarea(test, 2)
        replace_focused_text(test, "Создай заказ клиента для Ромашка на Кабель 10 штук")
        result["generatedTestClick"] = click_label(test, "Запустить тест")
        time.sleep(2)
        body = test._safe_body_text()
        result["generatedTestShowsTemplate"] = body_contains_any(body, ["has_dsl_template: true", "dsl_template_mode: hint"])

        exact_prompt = "Создание справочника Контрагенты. В комментарии указывай код контрагента. Подтверждение не нужно"
        result["catalogPromptFocus"] = focus_textarea(test, 0)
        replace_focused_text(test, exact_prompt)
        result["catalogPromptGenerateClick"] = click_label(test, "Сгенерировать JSON")
        time.sleep(3)
        catalog_json = read_textarea(test, 1)
        result["catalogPromptFull"] = exact_prompt in catalog_json
        result["catalogPromptNoTruncatedTrigger"] = 'Подтвер"' not in catalog_json and "Подтвер\n" not in catalog_json
        result["catalogPromptRiskWrite"] = '"risk_level": "write"' in catalog_json
        result["catalogPromptApprovalFalse"] = '"approval_required": false' in catalog_json
        result["catalogPromptCreateReference"] = '"CreateReference"' in catalog_json

        test._session_call("Page.navigate", {"url": skills_url})
        test._wait_until_text_contains("Skills", args.timeout_sec)
        time.sleep(1)
        result["systemOverwriteClick"] = click_label(test, "Сохранить")
        time.sleep(2)
        body = test._safe_body_text()
        result["systemOverwriteWarning"] = body_contains_any(body, ["Системный skill нельзя перезаписать", "нельзя перезаписать"])

        (artifact_dir / "web_skills_negative_ui_body.txt").write_text(body, encoding="utf-8")
        result["bodyHead"] = body[:1200]
        required = [
            "emptyDescriptionWarning",
            "invalidJsonWarning",
            "generatedHasTemplateVars",
            "generatedHasDslTemplate",
            "generatedHasTemplateMode",
            "generatedHasDocumentTarget",
            "generatedKeepsApprovalForDoNotWriteWithoutApproval",
            "generatedTestShowsTemplate",
            "catalogPromptFull",
            "catalogPromptNoTruncatedTrigger",
            "catalogPromptRiskWrite",
            "catalogPromptApprovalFalse",
            "catalogPromptCreateReference",
            "newSkillHasUserName",
            "newSkillNotSystem",
            "newSkillDisabled",
            "newSkillJsonEditable",
            "systemOverwriteWarning",
        ]
        result["success"] = all(bool(result.get(key)) for key in required)
        result["required"] = {key: bool(result.get(key)) for key in required}
        return result
    finally:
        test._close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Negative UI checks for AI Skills form")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "web_skills_artifacts"))
    parser.add_argument("--headed", action="store_true", help="Show Chrome window for manual debugging. Headless is default.")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_skills_negative_ui_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
