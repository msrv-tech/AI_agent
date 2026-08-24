# -*- coding: utf-8 -*-
"""UI E2E: created/changed object links refresh in the active agent form."""

from __future__ import annotations

import argparse
import base64
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
for _path in (REPO_ROOT, REPO_ROOT / "automation"):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_modes_e2e import bridge_execute
from automation.ui.web_agent_skill_e2e import close_font_dialog, focus_prompt, replace_focused_text
from automation.ui.web_document_recognition_e2e import (
    activate_agent_tab,
    bsl_string,
    dismiss_bp_update_info,
    inspect_created_links_panel,
    press_tab,
)
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-bp-demo"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-bp-demo";'


def create_dialog(bridge_url: str, marker: str) -> dict:
    code = (
        "СсылкаДиалога = ИИА_Сервер.СоздатьНовыйДиалог(ИИА_Сервер.ИмяТекущегоПользователя(), Перечисления.ИИА_ТипДиалога.РаспознаваниеДокументов);"
        "ДиалогОбъект = СсылкаДиалога.ПолучитьОбъект(); ДиалогОбъект.Наименование = " + bsl_string(marker) + "; ДиалогОбъект.Записать();"
        "ИИА_Сервер.ДобавитьСообщениеВДиалог(СсылкаДиалога, Перечисления.ИИА_АвторСообщения.Система, "
        "Перечисления.ИИА_ТипСообщения.Текст, "
        + bsl_string("Диалог подготовлен: " + marker)
        + ", \"\", \"\", 0);"
        "РезультатВыполнения = Новый Структура(\"dialog\", Строка(СсылкаДиалога));"
    )
    return bridge_execute(bridge_url, code)


def add_changed_object_to_dialog(bridge_url: str, marker: str) -> dict:
    object_name = marker + "_OBJECT"
    code = (
        "РезультатВыполнения = Новый Структура(\"found,objectPresentation\", Ложь, \"\");"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 1 Диалоги.Ссылка КАК Ссылка "
        "ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.Наименование = &Наименование "
        "УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"Наименование\", " + bsl_string(marker) + ");"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Если Выборка.Следующий() Тогда "
        "СсылкаДиалога = Выборка.Ссылка;"
        "Контрагент = Справочники.Контрагенты.СоздатьЭлемент();"
        "Контрагент.Наименование = " + bsl_string(object_name) + ";"
        "Контрагент.Записать();"
        "МассивСсылок = Новый Массив; МассивСсылок.Добавить(Контрагент.Ссылка);"
        "ИИА_Сервер.ДобавитьИзмененныеОбъекты(СсылкаДиалога, МассивСсылок);"
        "ИИА_Сервер.ДобавитьСообщениеВДиалог(СсылкаДиалога, Перечисления.ИИА_АвторСообщения.Система, "
        "Перечисления.ИИА_ТипСообщения.Текст, "
        "\"=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ===\" + Символы.ПС + Символы.ПС + "
        + bsl_string("Задача выполнена успешно. Созданные/измененные объекты: " + object_name)
        + ", \"\", \"\", 0);"
        "ПоследнийУИД = ИИА_Сервер.ПолучитьПоследнийУИДСообщенияДиалога(СсылкаДиалога);"
        "СообщениеРезюме = ИИА_Сервер.ПолучитьСообщениеПоУИД(СсылкаДиалога, ПоследнийУИД);"
        "Если СообщениеРезюме <> Неопределено Тогда "
        "ИИА_Сервер.УведомитьОбОбновленииДиалога(СсылкаДиалога, \"РезюмеДобавлено\", Новый Структура(\"Сообщение\", СообщениеРезюме));"
        "КонецЕсли;"
        "ДопДанные = Новый Структура(\"Успех\", Истина);"
        "ДопДанные.Вставить(\"ИзмененныеОбъектыПредставления\", ИИА_Сервер.ПолучитьПредставленияИзмененныхОбъектовДиалога(СсылкаДиалога));"
        "ДопДанные.Вставить(\"ИзмененныеОбъектыНавигационныеСсылки\", ИИА_Сервер.ПолучитьНавигационныеСсылкиИзмененныхОбъектовДиалога(СсылкаДиалога));"
        "Если СообщениеРезюме <> Неопределено Тогда ДопДанные.Вставить(\"Сообщение\", СообщениеРезюме); КонецЕсли;"
        "ИИА_Сервер.УведомитьОбОбновленииДиалога(СсылкаДиалога, \"ЗадачаЗавершена\", ДопДанные);"
        "РезультатВыполнения.found = Истина;"
        "РезультатВыполнения.objectPresentation = Строка(Контрагент.Ссылка);"
        "КонецЕсли;"
    )
    return bridge_execute(bridge_url, code)


def activate_tab_by_marker(test: BrowserQuery1CTest, marker: str, timeout_sec: int) -> bool:
    script = r"""
((marker) => {
 const visible = (el) => {
   const r = el.getBoundingClientRect();
   const s = getComputedStyle(el);
   return r.width > 10 && r.height > 8 && r.x > -1000 && r.y > -1000
     && s.display !== 'none' && s.visibility !== 'hidden';
 };
 const markerPrefix = marker.slice(0, 18);
 const candidates = Array.from(document.querySelectorAll('div, span, a, button'))
   .filter(visible)
   .filter((el) => {
     const text = (el.innerText || el.title || '').replace(/\s+/g, ' ').trim();
     const r = el.getBoundingClientRect();
     return r.y < 80 && (text.includes(marker) || text.includes(markerPrefix) || /: Агент/.test(text));
   });
 if (!candidates.length) return false;
 const el = candidates.sort((a, b) => b.getBoundingClientRect().x - a.getBoundingClientRect().x)[0];
 const r = el.getBoundingClientRect();
 return JSON.stringify({x: Math.floor(r.x + r.width / 2), y: Math.floor(r.y + r.height / 2), text: el.innerText || el.title || ''});
})(""" + json.dumps(marker, ensure_ascii=False) + """)
"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        raw = test._evaluate(script)
        if raw and raw != "False":
            try:
                point = json.loads(raw)
            except json.JSONDecodeError:
                point = {}
            if point.get("x") is not None and point.get("y") is not None:
                x = int(point["x"])
                y = int(point["y"])
                test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
                test._session_call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "clickCount": 1})
                test._session_call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "clickCount": 1})
                time.sleep(1)
                return True
        if raw == "True":
            time.sleep(1)
            return True
        time.sleep(1)
    return False


def activate_previous_tab(test: BrowserQuery1CTest) -> None:
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 17, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 33, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 33, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 17})
    time.sleep(1)


def close_active_tab(test: BrowserQuery1CTest) -> None:
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 17, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 115, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 115, "modifiers": 2})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 17})
    time.sleep(2)


def wait_for_panel(test: BrowserQuery1CTest, presentation: str, timeout_sec: int) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = inspect_created_links_panel(test, [presentation])
        if int(last.get("matchedCount") or 0) > 0:
            return last | {"visible": True}
        time.sleep(1)
    return last | {"visible": False}


def inspect_created_links_anywhere(test: BrowserQuery1CTest, expected_presentations: list[str]) -> dict:
    expected = [value for value in expected_presentations if value]
    script = r"""
((expected) => {
 const visible = (el) => {
   const r = el.getBoundingClientRect();
   const s = getComputedStyle(el);
   return r.width > 10 && r.height > 8 && r.x > -1000 && r.y > -1000
     && s.display !== 'none' && s.visibility !== 'hidden';
 };
 const normalize = (text) => (text || '').replace(/\s+/g, ' ').trim();
 const nodes = Array.from(document.querySelectorAll('a, button, div, span, label, input')).filter(visible);
 const visibleNodes = nodes.map((el) => {
   const r = el.getBoundingClientRect();
   const text = normalize(el.innerText || el.value || el.title || el.getAttribute('aria-label') || '');
   return { text, x: r.x, y: r.y, width: r.width, height: r.height, tag: el.tagName };
 }).filter((item) => item.text);
 const header = visibleNodes.find((item) => item.text.includes('Созданные/измененные объекты'));
 const matches = [];
 for (const item of visibleNodes) {
   if (item.x < window.innerWidth * 0.70) continue;
   if (item.y < 180) continue;
   if (item.text.includes(': Агент') || item.text.includes('Текущий диалог')) continue;
   for (const presentation of expected) {
     if (presentation && item.text.includes(presentation)) {
       matches.push(item);
       break;
     }
   }
 }
 return JSON.stringify({
   headerVisible: !!header,
   expectedCount: expected.length,
   matchedCount: matches.length,
   matches,
   visibleTexts: visibleNodes.slice(0, 120).map((item) => item.text)
 });
})(""" + json.dumps(expected, ensure_ascii=False) + """)
"""
    raw = test._evaluate(script)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"parseError": raw}


def wait_for_visible_created_link(test: BrowserQuery1CTest, presentation: str, timeout_sec: int) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = inspect_created_links_anywhere(test, [presentation])
        if int(last.get("matchedCount") or 0) > 0:
            return last | {"visible": True}
        time.sleep(1)
    return last | {"visible": False}


def wait_for_agent_ready_strict(test: BrowserQuery1CTest, timeout_sec: int) -> bool:
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        body = test._safe_body_text()
        if (
            "Текущий диалог" in body
            and "Отправить" in body
            and ("Прикрепить файл" in body or "Опишите задачу" in body)
            and "К сожалению, возникла непредвиденная ситуация" not in body
        ):
            return True
        time.sleep(1)
    return False


def click_created_link_and_verify(test: BrowserQuery1CTest, presentation: str, timeout_sec: int) -> dict:
    dismiss_bp_update_info(test)
    panel = wait_for_visible_created_link(test, presentation, timeout_sec)
    matches = panel.get("matches") or []
    if not matches:
        return {"clicked": False, "opened": False, "reason": "missing-link", "panel": panel}
    candidates = [
        item for item in matches
        if str(item.get("text") or "").strip() == presentation
        and str(item.get("tag") or "").upper() in {"A", "BUTTON"}
    ]
    if not candidates:
        candidates = [item for item in matches if str(item.get("text") or "").strip() == presentation]
    item = candidates[0] if candidates else matches[0]
    x = int(float(item.get("x") or 0) + float(item.get("width") or 20) / 2)
    y = int(float(item.get("y") or 0) + float(item.get("height") or 20) / 2)
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    test._session_call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})
    time.sleep(0.5)
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 13})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 13})
    time.sleep(3)
    try:
        screenshot = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        (Path(test.config.artifact_dir) / "web_agent_created_link_after_click.png").write_bytes(base64.b64decode(screenshot["result"]["data"]))
    except Exception:
        pass
    script = r"""
((presentation) => {
 const visible = (el) => {
   const r = el.getBoundingClientRect();
   const s = getComputedStyle(el);
   return r.width > 10 && r.height > 8 && r.x > -1000 && r.y > -1000
     && s.display !== 'none' && s.visibility !== 'hidden';
 };
 const tabs = Array.from(document.querySelectorAll('.openedItem, .openlistItem')).filter(visible)
   .map((el) => (el.innerText || el.title || '').replace(/\s+/g, ' ').trim())
   .filter(Boolean);
 const headings = Array.from(document.querySelectorAll('div, span')).filter(visible)
   .filter((el) => {
     const r = el.getBoundingClientRect();
     return r.y < 220 && r.x > 120 && r.x < window.innerWidth * 0.85;
   })
   .map((el) => {
     const r = el.getBoundingClientRect();
     return {
       text: (el.innerText || el.title || '').replace(/\s+/g, ' ').trim(),
       x: r.x, y: r.y, width: r.width, height: r.height
     };
   })
   .filter((item) => item.text);
 const looksLikeObjectForm = (text) =>
   text.includes(presentation)
   && !/: Агент/.test(text)
   && !/Текущий диалог/.test(text)
   && !/Созданные\/измененные объекты/.test(text)
   && !/Задача выполнена успешно/.test(text)
   && !/Пользователь \[|Система \[/.test(text);
 const openedByTab = tabs.some(looksLikeObjectForm);
 const openedByHeader = headings.some((item) =>
   looksLikeObjectForm(item.text)
   && item.text.length <= presentation.length + 80
   && item.y < 180
 );
 const opened = openedByTab || openedByHeader;
 return JSON.stringify({opened, openedByTab, openedByHeader, tabs:tabs.slice(0,40), headings:headings.slice(0,80)});
})(""" + json.dumps(presentation, ensure_ascii=False) + """)
"""
    raw = test._evaluate(script)
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        state = {"parseError": raw, "opened": False}
    return {"clicked": True, "opened": bool(state.get("opened")), "click": {"x": x, "y": y, "text": item.get("text")}, "state": state}


def inspect_changed_objects_stored(bridge_url: str, marker: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура(\"found,count,presentations\", Ложь, 0, Новый Массив);"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 1 Диалоги.Ссылка КАК Ссылка "
        "ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.Наименование = &Наименование "
        "УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"Наименование\", " + bsl_string(marker) + ");"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Если Выборка.Следующий() Тогда "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект();"
        "РезультатВыполнения.found = Истина;"
        "РезультатВыполнения.count = Диалог.ИзмененныеОбъекты.Количество();"
        "Для Каждого СтрокаИзмененных Из Диалог.ИзмененныеОбъекты Цикл "
        "Если ЗначениеЗаполнено(СтрокаИзмененных.СсылкаНаОбъект) Тогда "
        "РезультатВыполнения.presentations.Добавить(Строка(СтрокаИзмененных.СсылкаНаОбъект));"
        "КонецЕсли; КонецЦикла;"
        "КонецЕсли;"
    )
    return bridge_execute(bridge_url, code)


def wait_for_summary_stable(test: BrowserQuery1CTest, marker: str, timeout_sec: int, stable_sec: int = 10) -> dict:
    deadline = time.time() + timeout_sec
    first_seen_at = 0.0
    observations: list[dict[str, object]] = []
    last_body = ""
    while time.time() < deadline:
        body = test._safe_body_text()
        last_body = body
        visible = marker in body and (
            "Задача выполнена успешно" in body
            or "Созданные/измененные объекты" in body
            or "Создано/изменено объектов" in body
        )
        observations.append({"t": round(time.time(), 3), "visible": visible, "bodyLength": len(body)})
        if visible:
            if not first_seen_at:
                first_seen_at = time.time()
            if time.time() - first_seen_at >= stable_sec:
                return {
                    "visible": True,
                    "stable": True,
                    "firstSeenAfterSec": round(first_seen_at - (deadline - timeout_sec), 1),
                    "observations": observations[-20:],
                    "bodyLength": len(body),
                }
        else:
            first_seen_at = 0.0
        time.sleep(1)
    return {
        "visible": False,
        "stable": False,
        "observations": observations[-20:],
        "bodyLength": len(last_body),
        "bodyHead": last_body[:1200],
    }


def set_top_prompt_text(test: BrowserQuery1CTest, text: str) -> dict:
    script = r"""
((text)=> {
 const visible=e=>{
   const r=e.getBoundingClientRect(),s=getComputedStyle(e);
   return r.width>300&&r.height>40&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden';
 };
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
   .map(e=>({e,r:e.getBoundingClientRect()}))
   .filter(x=>x.r.y < window.innerHeight * 0.35)
   .sort((a,b)=>a.r.y-b.r.y || b.r.width*b.r.height-a.r.width*a.r.height);
 if(!items.length) return JSON.stringify({ok:false, reason:'missing'});
 const e=items[0].e;
 e.scrollIntoView({block:'center', inline:'center'});
 e.focus();
 e.click();
 e.value=text;
 e.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
 e.dispatchEvent(new Event('change', {bubbles:true}));
 const r=e.getBoundingClientRect();
 return JSON.stringify({ok:true, value:e.value||'', x:r.x, y:r.y, width:r.width, height:r.height});
})(""" + json.dumps(text, ensure_ascii=False) + """)
"""
    raw = test._evaluate(script)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"parseError": raw}


def top_prompt_value(test: BrowserQuery1CTest) -> str:
    script = r"""
(()=> {
 const visible=e=>{
   const r=e.getBoundingClientRect(),s=getComputedStyle(e);
   return r.width>300&&r.height>40&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden';
 };
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
   .map(e=>({e,r:e.getBoundingClientRect()}))
   .filter(x=>x.r.y < window.innerHeight * 0.35)
   .sort((a,b)=>a.r.y-b.r.y || b.r.width*b.r.height-a.r.width*a.r.height);
 return items.length ? (items[0].e.value || '') : '';
})()
"""
    return str(test._evaluate(script) or "")


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    marker = args.marker or "E2E_LINK_REFRESH_" + time.strftime("%Y%m%d%H%M%S")
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
        log_file=str(artifact_dir / "web_agent_created_links_refresh_e2e.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    result: dict[str, object] = {"marker": marker}
    try:
        prepared = create_dialog(args.bridge_url, marker)
        result["prepared"] = prepared
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()
        test._login()
        test._open_agent_command()
        result["agentReadyAfterOpen"] = wait_for_agent_ready_strict(test, args.timeout_sec)
        result["agentTabActivated"] = result["agentReadyAfterOpen"] or activate_agent_tab(test, min(args.timeout_sec, 10))
        if result["agentTabActivated"]:
            result["agentReadyAfterActivate"] = wait_for_agent_ready_strict(test, args.timeout_sec)
        result["markerTabActivated"] = marker in test._safe_body_text()
        if not result["markerTabActivated"]:
            result["markerTabReactivated"] = activate_tab_by_marker(test, marker, min(args.timeout_sec, 10))
        try:
            result["agentFormReady"] = wait_for_agent_ready_strict(test, args.timeout_sec)
            if not result["agentFormReady"]:
                raise RuntimeError("Форма агента не достигла рабочего состояния.")
        except Exception as error:
            result["agentFormReady"] = False
            result["agentFormReadyError"] = str(error)
        if not result.get("agentFormReady"):
            body = test._safe_body_text()
            result["bodyHead"] = body[:2000]
            result["success"] = False
            try:
                screenshot = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
                (artifact_dir / "web_agent_not_ready.png").write_bytes(base64.b64decode(screenshot["result"]["data"]))
            except Exception:
                pass
            return result
        time.sleep(2)
        sticky_prompt = "INPUT_STICKY_" + marker
        result["promptFocusBeforeLiveUpdate"] = focus_prompt(test)
        replace_focused_text(test, sticky_prompt)
        press_tab(test)
        result["promptBeforeLiveUpdate"] = top_prompt_value(test)
        if sticky_prompt not in str(result["promptBeforeLiveUpdate"]):
            result["promptSetBeforeLiveUpdateFallback"] = set_top_prompt_text(test, sticky_prompt)
            result["promptBeforeLiveUpdateFallback"] = top_prompt_value(test)
        live_update = add_changed_object_to_dialog(args.bridge_url, marker)
        result["liveUpdate"] = live_update
        presentation = str(live_update.get("objectPresentation") or marker)
        result["summaryStable"] = wait_for_summary_stable(test, marker, args.timeout_sec, args.stable_sec)
        result["promptAfterLiveUpdate"] = top_prompt_value(test)
        try:
            screenshot = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
            (artifact_dir / "web_agent_created_links_refresh.png").write_bytes(base64.b64decode(screenshot["result"]["data"]))
        except Exception:
            pass
        body = test._safe_body_text()
        result["bodyHasMarker"] = marker in body
        result["createdLinksPanel"] = wait_for_panel(test, presentation, args.timeout_sec)
        result["createdLinkVisible"] = wait_for_visible_created_link(test, presentation, args.timeout_sec)
        result["createdLinkClick"] = click_created_link_and_verify(test, presentation, 10)
        result["changedObjectsStored"] = inspect_changed_objects_stored(args.bridge_url, marker)
        result["promptPreserved"] = sticky_prompt in str(result["promptAfterLiveUpdate"])
        result["success"] = (
            bool(result["summaryStable"].get("stable"))
            and marker in body
            and int(result["changedObjectsStored"].get("count") or 0) > 0
            and bool(result["createdLinkVisible"].get("visible"))
            and bool(result["createdLinkClick"].get("opened"))
            and bool(result["promptPreserved"])
        )
        (artifact_dir / "web_agent_created_links_refresh_body.txt").write_text(body, encoding="utf-8")
        return result
    finally:
        test._close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="UI E2E for created object links refresh in active agent form")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--marker", default="")
    parser.add_argument("--timeout-sec", type=int, default=40)
    parser.add_argument("--stable-sec", type=int, default=10)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "created_links_refresh"))
    parser.add_argument("--headed", action="store_true")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_agent_created_links_refresh_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
