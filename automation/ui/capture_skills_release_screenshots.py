# -*- coding: utf-8 -*-
"""Capture Infostart release screenshots for the skills workflow."""

from __future__ import annotations

import argparse
import base64
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
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
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


def capture_png(test: BrowserQuery1CTest, path: Path) -> None:
    test._session_call(
        "Emulation.setDeviceMetricsOverride",
        {"width": 1366, "height": 768, "deviceScaleFactor": 1, "mobile": False},
    )
    time.sleep(1)
    response = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
    path.write_bytes(base64.b64decode(response["result"]["data"]))


def reveal_json_fragment(test: BrowserQuery1CTest, fragment: str) -> str:
    encoded = json.dumps(fragment, ensure_ascii=False)
    script = r"""
((fragment)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 const jsonEditor=items.find(e=>(e.value||'').includes(fragment));
 if(!jsonEditor) return 'missing:' + items.length;
 const index=jsonEditor.value.indexOf(fragment);
 const ratio=Math.max(0, index) / Math.max(1, jsonEditor.value.length);
 jsonEditor.scrollTop=Math.max(0, jsonEditor.scrollHeight*ratio-jsonEditor.clientHeight*0.25);
 return 'revealed:' + index + ':' + jsonEditor.value.length;
})(""" + encoded + ")"
    return test._evaluate(script)


def open_command(test: BrowserQuery1CTest, web_url: str, command_name: str, wait_text: str, timeout_sec: int) -> None:
    encoded = urllib.parse.quote(command_name, safe=".")
    test._session_call("Page.navigate", {"url": web_url.rstrip("/") + "/#e1cib/command/" + encoded})
    test._wait_until_text_contains(wait_text, timeout_sec)
    time.sleep(3)


def run(args: argparse.Namespace) -> dict:
    media_dir = Path(args.media_dir)
    media_dir.mkdir(parents=True, exist_ok=True)
    result: dict[str, object] = {"mediaDir": str(media_dir)}
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
        log_file=str(media_dir / "capture_skills_release_screenshots.log"),
        artifact_dir=str(media_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    try:
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()

        open_command(test, args.web_url, "CommonCommand.ИИА_Skills", "Skills", args.timeout_sec)
        description = (
            "Создать skill для документа ЗаказПокупателя: находить контрагента и номенклатуру "
            "по названию, заполнять заказ клиента, количество и цену, перед записью требовать подтверждение."
        )
        result["descriptionFocus"] = focus_textarea(test, 0)
        replace_focused_text(test, description)
        result["generateClick"] = click_label(test, "Сгенерировать JSON")
        time.sleep(4)

        result["testFocus"] = focus_textarea(test, 2)
        replace_focused_text(test, "Создай заказ клиента для Ромашка на Кабель 10 штук")
        result["testClick"] = click_label(test, "Запустить тест")
        time.sleep(3)
        result["jsonReveal"] = reveal_json_fragment(test, '"dsl_template"')
        time.sleep(1)
        capture_png(test, media_dir / "skills_dsl_workflow.png")

        result["success"] = (media_dir / "skills_dsl_workflow.png").exists()
        return result
    finally:
        test._close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture release screenshots for Infostart article")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--timeout-sec", type=int, default=70)
    parser.add_argument("--agent-wait-sec", type=int, default=30)
    parser.add_argument("--media-dir", default=str(REPO_ROOT / "docs" / "articles" / "product_0_9_0_skills" / "media"))
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.media_dir) / "capture_skills_release_screenshots_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
