# -*- coding: utf-8 -*-
"""Regression E2E for the agent result-table hyperlink in 1C web client."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT, REPO_ROOT / "automation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_modes_e2e import send_prompt, switch_mode
from automation.ui.web_com_gate import open_agent_form
from automation.ui.web_document_recognition_e2e import wait_for_agent_state
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


LINK_CAPTIONS = ["Открыть таблицу результатов", "Открыть результат"]


def observe(test: BrowserQuery1CTest, captions: list[str]) -> dict:
    expression = r"""
(() => {
  const captions = %s;
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && r.x >= 0 && r.y >= 0
      && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const nodes = Array.from(document.querySelectorAll('a,button,div,span,label,input')).filter(visible);
  const match = nodes.find((el) => captions.includes((el.innerText || el.value || '').trim()));
  const body = document.body ? document.body.innerText || '' : '';
  return JSON.stringify({
    linkVisible: Boolean(match),
    linkText: match ? (match.innerText || match.value || '').trim() : '',
    resultTabVisible: body.includes('Таблица результатов'),
    bodyLength: body.length
  });
})()
""" % json.dumps(captions, ensure_ascii=False)
    return json.loads(str(test._evaluate(expression)))


def wait_for_link(test: BrowserQuery1CTest, timeout_sec: int, observations: list[dict]) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = observe(test, LINK_CAPTIONS)
        observations.append({"checkpoint": "result-link", "time": round(time.time(), 3), **last})
        if last.get("linkVisible"):
            return last
        time.sleep(2)
    return last


def return_to_agent_form(test: BrowserQuery1CTest, timeout_sec: int) -> None:
    """Return from the automatically opened tabular document to the agent tab."""
    clicked = test._evaluate(
        r"""
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 2 && r.height > 2 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const tabs = Array.from(document.querySelectorAll('.openedItem, .openlistItem')).filter(visible);
  const tab = tabs.find((el) => (el.innerText || el.title || '').includes('ИИ Агент'));
  if (!tab) return 'missing';
  const target = tab.querySelector('a,button') || tab;
  const r = target.getBoundingClientRect();
  ['pointerdown','mousedown','mouseup','click'].forEach((type) => target.dispatchEvent(
    new MouseEvent(type, {bubbles:true, cancelable:true, view:window, clientX:r.x+r.width/2, clientY:r.y+r.height/2})
  ));
  return 'clicked';
})()
"""
    )
    if clicked == "clicked" and test._wait_for_agent_form(timeout_sec):
        return
    open_agent_form(test, test.config.web_url, timeout_sec)


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    observations: list[dict] = []
    config = WebUiConfig(
        web_url=args.web_url,
        chrome_exe=args.chrome_exe,
        base_path="",
        user=args.user,
        password=args.password,
        query_text="",
        query_params_json="",
        expected_text="",
        timeout_sec=args.timeout_sec,
        log_file=str(artifact_dir / "web_result_table_link_e2e.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    result: dict = {"passed": False, "prompt": args.prompt}
    try:
        test._launch_browser()
        test._open_initial_target()
        test._login()
        open_agent_form(test, args.web_url, args.timeout_sec)
        switch_mode(test, "Агент")
        send_prompt(test, args.prompt)
        state = wait_for_agent_state(test, args.agent_wait_sec, auto_confirm=True)
        observations.append({"checkpoint": "agent-complete", "time": round(time.time(), 3), "state": state.get("state")})
        if observe(test, LINK_CAPTIONS).get("resultTabVisible"):
            return_to_agent_form(test, args.timeout_sec)
            observations.append({"checkpoint": "agent-returned", "time": round(time.time(), 3)})
        link = wait_for_link(test, args.timeout_sec, observations)
        if not link.get("linkVisible"):
            raise AssertionError("После успешного табличного запроса не показана ссылка открытия результата")
        if not test._click_visible_text(LINK_CAPTIONS):
            raise AssertionError("Ссылка результата видима, но клик по ней не выполнен")
        test._wait_until_any_text_contains(["Таблица результатов"], args.timeout_sec)
        opened = observe(test, LINK_CAPTIONS)
        observations.append({"checkpoint": "result-opened", "time": round(time.time(), 3), **opened})
        if not opened.get("resultTabVisible"):
            raise AssertionError("После клика не открыта форма 'Таблица результатов'")
        result.update({"passed": True, "link": link, "opened": opened})
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        test._close()
        with (artifact_dir / "web_result_table_link_e2e_observations.jsonl").open("w", encoding="utf-8") as stream:
            for item in observations:
                stream.write(json.dumps(item, ensure_ascii=False) + "\n")
        result_file = artifact_dir / "web_result_table_link_e2e_result.json"
        result_file.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        result["result_file"] = str(result_file)
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check result-table hyperlink lifecycle in the 1C agent form")
    parser.add_argument("--web-url", default=os.getenv("FRESH_CLOUD_WEB_URL", ""))
    parser.add_argument("--user", default=os.getenv("FRESH_CLOUD_USER", ""))
    parser.add_argument("--password", default=os.getenv("FRESH_CLOUD_PASSWORD", ""))
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--prompt", default="Покажи первые 5 контрагентов: наименование и ИНН")
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "result_table_link"))
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--agent-wait-sec", type=int, default=180)
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    if not args.web_url or not args.user:
        print("Задайте --web-url/--user или FRESH_CLOUD_WEB_URL/FRESH_CLOUD_USER.", file=sys.stderr)
        return 2
    result = run(args)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
