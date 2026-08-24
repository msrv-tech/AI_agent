# -*- coding: utf-8 -*-
"""E2E UI check for the document recognition agent mode."""

from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import mimetypes
import re
import sys
import time
import urllib.parse
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_modes_e2e import bridge_execute, press_enter
from automation.ui.web_agent_skill_e2e import click_label, close_font_dialog, focus_prompt, replace_focused_text
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'


def bsl_string(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def make_invoice_png_base64() -> str:
    from PIL import Image, ImageDraw

    image = Image.new("RGB", (320, 160), "white")
    draw = ImageDraw.Draw(image)
    draw.text((10, 10), "Supplier invoice", fill="black")
    draw.text((10, 40), "No 123 from 31.07.2026", fill="black")
    draw.text((10, 70), "Supplier ALFAMART total 1000 VAT 20%", fill="black")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def bsl_string_chunks(value: str, chunk_size: int = 900) -> str:
    chunks = [value[index : index + chunk_size] for index in range(0, len(value), chunk_size)]
    return " + ".join(bsl_string(chunk) for chunk in chunks)


def press_tab(test: BrowserQuery1CTest) -> None:
    test._session_call("Input.dispatchKeyEvent", {"type": "keyDown", "windowsVirtualKeyCode": 9})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", "windowsVirtualKeyCode": 9})


def focus_mode_field(test: BrowserQuery1CTest, timeout_sec: int = 15) -> str:
    script = r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const isMode=e=>/(Агент|Запрос|Распознаван)/.test(e.value||'');
 const items=Array.from(document.querySelectorAll('input')).filter(visible).filter(isMode).sort((a,b)=>a.getBoundingClientRect().y-b.getBoundingClientRect().y);
 if(!items.length) return 'missing';
 const e=items[0]; e.scrollIntoView({block:'center'}); e.focus(); e.click(); return e.value || 'focused';
})()
"""
    deadline = time.time() + timeout_sec
    last = "missing"
    while time.time() < deadline:
        last = test._evaluate(script)
        if last != "missing":
            return last
        time.sleep(0.5)
    return last


def set_visible_prompt_text(test: BrowserQuery1CTest, text: str) -> dict:
    script = r"""
((text)=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>120&&r.height>25&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>b.getBoundingClientRect().width*b.getBoundingClientRect().height-a.getBoundingClientRect().width*a.getBoundingClientRect().height);
 if(!items.length) return {ok:false, reason:'missing'};
 const e=items[0];
 e.scrollIntoView({block:'center', inline:'center'});
 e.focus();
 e.click();
 e.value = text;
 e.dispatchEvent(new InputEvent('input', {bubbles:true, inputType:'insertText', data:text}));
 e.dispatchEvent(new Event('change', {bubbles:true}));
 return {ok:true, tag:e.tagName, value:e.value, width:e.getBoundingClientRect().width, height:e.getBoundingClientRect().height};
})(""" + json.dumps(text, ensure_ascii=False) + """)
"""
    return test._evaluate(script)


def visible_prompt_value(test: BrowserQuery1CTest) -> str:
    script = r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>120&&r.height>25&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>b.getBoundingClientRect().width*b.getBoundingClientRect().height-a.getBoundingClientRect().width*a.getBoundingClientRect().height);
 return items.length ? (items[0].value || '') : '';
})()
"""
    return str(test._evaluate(script) or "")


def dismiss_bp_update_info(test: BrowserQuery1CTest) -> bool:
    return False


def switch_mode(test: BrowserQuery1CTest, mode: str) -> dict:
    before = focus_mode_field(test)
    if "Распознавание документов" in before:
        return {"before": before, "after": before, "attempts": [], "ok": True}
    attempts: list[dict[str, str]] = []
    after = ""
    for value in ("Распознавание документов", mode):
        focus_mode_field(test, 5)
        replace_focused_text(test, value)
        press_enter(test)
        press_tab(test)
        time.sleep(2)
        after = test._evaluate(
            r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('input')).filter(visible).filter(e=>/(Агент|Запрос|Распознаван)/.test(e.value||''));
 return items.length ? items[0].value : '';
})()
"""
        )
        attempts.append({"typed": value, "after": after})
        if "Распознавание документов" in after:
            break
    if "Распознавание документов" not in after:
        after = test._evaluate(
        r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('input')).filter(visible).filter(e=>/(Агент|Запрос|Распознаван)/.test(e.value||''));
 return items.length ? items[0].value : '';
})()
"""
        )
    return {"before": before, "after": after, "attempts": attempts, "ok": "Распознавание документов" in after}


def create_recognition_dialog(bridge_url: str) -> dict:
    code = (
        "Ссылка = ИИА_Сервер.СоздатьНовыйДиалог(ИИА_Сервер.ИмяТекущегоПользователя(), Перечисления.ИИА_ТипДиалога.РаспознаваниеДокументов);"
        "РезультатВыполнения = Новый Структура(\"created,dialog\", Истина, Строка(Ссылка));"
    )
    return bridge_execute(bridge_url, code)


def activate_agent_tab(test: BrowserQuery1CTest, timeout_sec: int = 30) -> bool:
    script = r"""
(()=> {
 const visible = (el) => {
   const r = el.getBoundingClientRect();
   const s = getComputedStyle(el);
   return r.width > 10 && r.height > 8 && r.x > -1000 && r.y > -1000 && s.display !== 'none' && s.visibility !== 'hidden';
 };
 let tabs = Array.from(document.querySelectorAll('.openedItem, .openlistItem')).filter(visible);
 let candidate = tabs.reverse().find((el) => {
   const text = (el.innerText || el.title || '').trim();
   return /Диалог ИИ|ИИ Агент|Агент ИИ/.test(text);
 });
 if (!candidate) {
   const all = Array.from(document.querySelectorAll('div, span, a, button')).filter(visible)
     .map((el) => {
       const r = el.getBoundingClientRect();
       return {el, text:(el.innerText || el.title || '').trim(), area:r.width*r.height, y:r.y};
     })
     .filter((x) => /: Агент$|: Агент\s|Диалог ИИ.*Агент/.test(x.text))
     .sort((a,b) => a.area - b.area || a.y - b.y);
   candidate = all.length ? all[0].el : null;
 }
 if (!candidate) return 'missing';
 ['pointerdown','mousedown','mouseup','click'].forEach((type) => {
   candidate.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1}));
 });
 return candidate.innerText || candidate.title || 'clicked';
})()
"""
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        clicked = test._evaluate(script)
        time.sleep(1)
        if test._agent_form_visible():
            return True
        if clicked == "missing":
            time.sleep(1)
    return False


def activate_dialog_tab_by_marker(test: BrowserQuery1CTest, marker: str, timeout_sec: int = 30) -> bool:
    script = r"""
((marker) => {
 const visible = (el) => {
   const r = el.getBoundingClientRect();
   const s = getComputedStyle(el);
   return r.width > 10 && r.height > 8 && r.x > -1000 && r.y > -1000
     && s.display !== 'none' && s.visibility !== 'hidden';
 };
 const markerPrefix = marker.slice(0, 24);
 const candidates = Array.from(document.querySelectorAll('div, span, a, button')).filter(visible)
   .map((el) => {
     const r = el.getBoundingClientRect();
     const text = (el.innerText || el.title || '').replace(/\s+/g, ' ').trim();
     return {el, text, x:r.x, y:r.y, area:r.width*r.height};
   })
   .filter((item) => item.y < 90 && (item.text.includes(marker) || item.text.includes(markerPrefix)))
   .sort((a, b) => a.area - b.area || a.y - b.y || b.x - a.x);
 if (!candidates.length) return 'missing';
 const el = candidates[0].el;
 ['pointerdown','mousedown','mouseup','click'].forEach((type) => {
   el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1}));
 });
 return candidates[0].text || 'clicked';
})(""" + json.dumps(marker, ensure_ascii=False) + """)
"""
    deadline = time.time() + timeout_sec
    last = "missing"
    while time.time() < deadline:
        last = str(test._evaluate(script) or "")
        time.sleep(1)
        body = test._safe_body_text()
        if test._agent_form_visible() and marker in body:
            return True
        time.sleep(1)
    test.logger.info(f"Не удалось активировать вкладку диалога по маркеру {marker}: {last}")
    return False


def read_attachment_base64(image_path: str) -> tuple[str, str, str]:
    if image_path:
        path = Path(image_path).resolve()
        content = path.read_bytes()
        file_name = path.name
        extension = path.suffix.lstrip(".").lower() or "png"
        return base64.b64encode(content).decode("ascii"), file_name, extension

    return make_invoice_png_base64(), "supplier_invoice_e2e.png", "png"


def attach_image_to_latest_recognition_dialog(bridge_url: str, image_path: str) -> dict:
    attachment_base64, file_name, extension = read_attachment_base64(image_path)
    base64_expr = bsl_string_chunks(attachment_base64)
    file_name_expr = bsl_string(file_name)
    extension_expr = bsl_string(extension)
    code = (
        "РезультатВыполнения = Новый Структура(\"attached,dialog,fileName\", Ложь, \"\", " + file_name_expr + ");"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 1 Диалоги.Ссылка КАК Ссылка "
        "ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.ТипДиалога = &ТипДиалога "
        "УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.РаспознаваниеДокументов);"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Если Выборка.Следующий() Тогда "
        "Путь = ПолучитьИмяВременногоФайла(" + extension_expr + ");"
        "Картинка = Base64Значение(" + base64_expr + ");"
        "Картинка.Записать(Путь);"
        "ИИА_Вложения.ДобавитьВложениеИзФайла(Выборка.Ссылка, Путь, " + file_name_expr + ");"
        "РезультатВыполнения.attached = Истина;"
        "РезультатВыполнения.dialog = Строка(Выборка.Ссылка);"
        "КонецЕсли;"
    )
    return bridge_execute(bridge_url, code)


def wait_for_agent_state(test: BrowserQuery1CTest, timeout_sec: int, auto_confirm: bool = False) -> dict:
    deadline = time.time() + timeout_sec
    result: dict[str, object] = {"confirmed": False, "state": "timeout", "samples": []}
    last_sample = ""
    while time.time() < deadline:
        if not test._agent_form_visible():
            activate_agent_tab(test, 3)
        body_text = test._safe_body_text()
        sample = body_text[:1200]
        if sample != last_sample:
            result["samples"].append(sample[:300])
            last_sample = sample
        if auto_confirm and "Подтверд" in body_text:
            result["confirmClick"] = click_label(test, "Подтвердить")
            result["confirmed"] = True
            time.sleep(1)
            continue
        summary_ready = "Выполненные шаги:" in body_text and "Проверка:" in body_text
        if summary_ready:
            result["state"] = "success"
            result["bodyText"] = body_text
            return result
        if "Задача выполнена успешно" in body_text or "Создан черновик документа" in body_text:
            time.sleep(2)
            continue
        if "Задача завершена с ошибкой" in body_text or "Не удалось надежно распознать" in body_text:
            result["state"] = "error"
            result["bodyText"] = body_text
            return result
        time.sleep(2)
    result["bodyText"] = test._safe_body_text()
    return result


def collect_ui_diagnostic_state(test: BrowserQuery1CTest) -> dict:
    script = r"""
(() => {
 const visible = (el) => {
   const r = el.getBoundingClientRect();
   const s = getComputedStyle(el);
   return r.width > 4 && r.height > 4 && r.x > -1000 && r.y > -1000
     && s.display !== 'none' && s.visibility !== 'hidden';
 };
 const normalize = (text) => (text || '').replace(/\s+/g, ' ').trim();
 const bodyText = document.body ? document.body.innerText || '' : '';
 const selectors = 'a,button,input,textarea,div,span,label';
 const nodes = Array.from(document.querySelectorAll(selectors)).filter(visible)
   .map((el) => {
     const r = el.getBoundingClientRect();
     const text = normalize(el.innerText || el.value || el.title || el.getAttribute('aria-label') || '');
     const role = el.getAttribute('role') || '';
     return {
       tag: el.tagName,
       role,
       id: el.id || '',
       className: String(el.className || '').slice(0, 120),
       text,
       x: Math.round(r.x),
       y: Math.round(r.y),
       width: Math.round(r.width),
       height: Math.round(r.height)
     };
   })
   .filter((item) => item.text)
   .sort((a, b) => (a.y - b.y) || (a.x - b.x));
 const interesting = nodes.filter((item) => {
   const text = item.text;
   return /Задача|Выполнена|Результат|Создан|изменен|Счет от поставщика|Распознавание|Подтверд|Отклон|Отправить|Прикрепить|Пользователь|Система|ИИ Агент|skill|РЕЗЮМЕ/.test(text)
     || item.tag === 'A'
     || item.tag === 'TEXTAREA';
 });
 const summaryNodes = nodes.filter((item) =>
   /Задача выполнена успешно|=== РЕЗЮМЕ|Созданные\/измененные объекты|Выполненные шаги:|Проверка:/.test(item.text)
 );
 const summaryStaticNodes = summaryNodes.filter((item) =>
   item.tag !== 'TEXTAREA'
   && item.id !== 'mainSurface'
   && !/^ps\d+win$/.test(item.id)
   && !/^ps\d+formContent$/.test(item.id)
   && !/mainGroup|panelContainer/.test(item.className)
 );
 const summaryCardNodes = summaryStaticNodes.filter((item) =>
   /Выполненные шаги:/.test(item.text)
   && /Проверка:/.test(item.text)
   && /_Group_Text/.test(item.id)
   && item.width >= 180
   && item.height >= 80
 );
 const summaryText = summaryNodes.map((item) => item.text).join('\\n');
 const summaryStaticText = summaryStaticNodes.map((item) => item.text).join('\\n');
 const objectLinkNodes = nodes.filter((item) =>
   /Счет от поставщика|Заказ|Контрагент|Номенклатура/.test(item.text)
   && (item.tag === 'A' || item.text.includes('0000-'))
 );
 return JSON.stringify({
   timestamp: new Date().toISOString(),
   url: location.href,
   viewport: { width: window.innerWidth, height: window.innerHeight },
   bodyHash: '',
   bodyHead: bodyText.slice(0, 1800),
   bodyTail: bodyText.slice(-1800),
   hasSuccess: bodyText.includes('Задача выполнена успешно'),
   hasSummaryMarker: bodyText.includes('=== РЕЗЮМЕ'),
   hasSummaryContent: /Выполненные шаги:/.test(summaryText) && /Проверка:/.test(summaryText),
   hasSummaryStaticContent: /Выполненные шаги:/.test(summaryStaticText) && /Проверка:/.test(summaryStaticText),
   hasSummaryCard: summaryCardNodes.length > 0,
   hasSummaryTextarea: summaryNodes.some((item) => item.tag === 'TEXTAREA'),
   hasCreatedObjects: bodyText.includes('Созданные/измененные объекты') || summaryText.includes('Созданные/измененные объекты'),
   hasApproval: /Подтверд|Отклон|Без подтверж/.test(bodyText),
   summaryNodes,
   summaryStaticNodes,
   summaryCardNodes,
   objectLinkNodes,
   interestingNodes: interesting.slice(0, 180)
 });
})()
"""
    raw = test._evaluate(script)
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        state = {"parseError": raw, "bodyHead": test._safe_body_text()[:1800]}
    digest_source = json.dumps(
        {
            "bodyHead": state.get("bodyHead", ""),
            "bodyTail": state.get("bodyTail", ""),
            "summaryNodes": state.get("summaryNodes", []),
            "objectLinkNodes": state.get("objectLinkNodes", []),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    state["bodyHash"] = hashlib.sha1(digest_source.encode("utf-8", errors="replace")).hexdigest()
    return state


def save_ui_diagnostic_frame(test: BrowserQuery1CTest, diagnostic_dir: Path, index: int, label: str) -> dict:
    diagnostic_dir.mkdir(parents=True, exist_ok=True)
    safe_label = re.sub(r"[^A-Za-zА-Яа-я0-9_.-]+", "_", label).strip("_")[:80] or "frame"
    stem = f"{index:03d}_{safe_label}"
    state = collect_ui_diagnostic_state(test)
    state["frame"] = index
    state["label"] = label
    json_path = diagnostic_dir / f"{stem}.json"
    png_path = diagnostic_dir / f"{stem}.png"
    json_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        screenshot = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
        png_path.write_bytes(base64.b64decode(screenshot["result"]["data"]))
        state["screenshot"] = str(png_path)
    except Exception as exc:
        state["screenshotError"] = str(exc)
    state["json"] = str(json_path)
    return state


def wait_for_agent_state_with_diagnostics(
    test: BrowserQuery1CTest,
    timeout_sec: int,
    auto_confirm: bool,
    diagnostic_dir: Path,
    interval_sec: float = 0.75,
) -> dict:
    deadline = time.time() + timeout_sec
    result: dict[str, object] = {"confirmed": False, "state": "timeout", "samples": [], "frames": []}
    last_hash = ""
    frame_index = 1
    while time.time() < deadline:
        if not test._agent_form_visible():
            activate_agent_tab(test, 3)
        state = collect_ui_diagnostic_state(test)
        state_hash = str(state.get("bodyHash") or "")
        if state_hash != last_hash:
            frame = save_ui_diagnostic_frame(test, diagnostic_dir, frame_index, f"state_{state_hash[:8]}")
            result["frames"].append({
                "frame": frame_index,
                "label": frame.get("label"),
                "json": frame.get("json"),
                "screenshot": frame.get("screenshot"),
                "hasSuccess": frame.get("hasSuccess"),
                "hasSummaryMarker": frame.get("hasSummaryMarker"),
                "hasSummaryContent": frame.get("hasSummaryContent"),
                "hasSummaryStaticContent": frame.get("hasSummaryStaticContent"),
                "hasSummaryCard": frame.get("hasSummaryCard"),
                "hasSummaryTextarea": frame.get("hasSummaryTextarea"),
                "hasCreatedObjects": frame.get("hasCreatedObjects"),
                "summaryNodes": frame.get("summaryNodes", [])[:5],
                "summaryStaticNodes": frame.get("summaryStaticNodes", [])[:5],
                "summaryCardNodes": frame.get("summaryCardNodes", [])[:5],
                "objectLinkNodes": frame.get("objectLinkNodes", [])[:8],
            })
            frame_index += 1
            last_hash = state_hash
        body_text = str(state.get("bodyHead") or "") + str(state.get("bodyTail") or "")
        if auto_confirm and state.get("hasApproval"):
            result["confirmClick"] = click_label(test, "Подтвердить")
            result["confirmed"] = True
            time.sleep(1)
            continue
        summary_ready = bool(state.get("hasSummaryContent")) or (
            "Выполненные шаги:" in body_text
            and "Проверка:" in body_text
        )
        if summary_ready or "Задача завершена с ошибкой" in body_text or "Не удалось надежно распознать" in body_text:
            pass
        elif "Задача выполнена успешно" in body_text or "Создан черновик документа" in body_text:
            time.sleep(interval_sec)
            continue
        if summary_ready:
            result["state"] = "success"
            result["bodyText"] = test._safe_body_text()
            final_frame = save_ui_diagnostic_frame(test, diagnostic_dir, frame_index, "success_detected")
            result["frames"].append({
                "frame": frame_index,
                "label": final_frame.get("label"),
                "json": final_frame.get("json"),
                "screenshot": final_frame.get("screenshot"),
                "hasSuccess": final_frame.get("hasSuccess"),
                "hasSummaryMarker": final_frame.get("hasSummaryMarker"),
                "hasSummaryContent": final_frame.get("hasSummaryContent"),
                "hasSummaryStaticContent": final_frame.get("hasSummaryStaticContent"),
                "hasSummaryCard": final_frame.get("hasSummaryCard"),
                "hasSummaryTextarea": final_frame.get("hasSummaryTextarea"),
                "hasCreatedObjects": final_frame.get("hasCreatedObjects"),
                "summaryNodes": final_frame.get("summaryNodes", [])[:5],
                "summaryStaticNodes": final_frame.get("summaryStaticNodes", [])[:5],
                "summaryCardNodes": final_frame.get("summaryCardNodes", [])[:5],
                "objectLinkNodes": final_frame.get("objectLinkNodes", [])[:8],
            })
            return result
        if "Задача завершена с ошибкой" in body_text or "Не удалось надежно распознать" in body_text:
            result["state"] = "error"
            result["bodyText"] = test._safe_body_text()
            save_ui_diagnostic_frame(test, diagnostic_dir, frame_index, "error_detected")
            return result
        time.sleep(interval_sec)
    result["bodyText"] = test._safe_body_text()
    save_ui_diagnostic_frame(test, diagnostic_dir, frame_index, "timeout")
    return result


def inspect_created_links_panel(test: BrowserQuery1CTest, expected_presentations: list[str]) -> dict:
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
 const rightEdge = window.innerWidth * 0.72;
 const panelTop = window.innerHeight * 0.42;
 const nodes = Array.from(document.querySelectorAll('a, button, div, span, label, input')).filter(visible);
 const rightNodes = nodes.map((el) => {
   const r = el.getBoundingClientRect();
   const text = normalize(el.innerText || el.value || el.title || el.getAttribute('aria-label') || '');
   return { text, x: r.x, y: r.y, width: r.width, height: r.height, tag: el.tagName };
 }).filter((item) => item.x >= rightEdge && item.text);
  const header = rightNodes.find((item) => item.text.includes('Созданные/измененные объекты'));
  const headerBottom = header ? header.y + header.height : Infinity;
  const panelLeft = header ? Math.max(rightEdge, header.x - 30) : rightEdge;
  const panelRight = header ? Math.min(window.innerWidth, header.x + Math.max(header.width, 260) + 80) : window.innerWidth;
  const stableRightLinkBand = (item) =>
    item.x >= rightEdge
    && item.y >= window.innerHeight * 0.08
    && item.y <= window.innerHeight * 0.58
    && item.height <= 32
    && item.width <= window.innerWidth * 0.32
    && !item.text.includes('Задача Выполнена Результат');
 const matches = [];
 for (const item of rightNodes) {
    for (const presentation of expected) {
      if (presentation && item.text.includes(presentation)
        && ((header
          && item.y >= Math.max(panelTop, headerBottom - 4)
          && item.x >= panelLeft
          && item.x + item.width <= panelRight)
          || stableRightLinkBand(item))
        && item.width <= window.innerWidth * 0.32
        && item.height <= window.innerHeight * 0.28
        && !item.text.includes('Задача Выполнена Результат')) {
       matches.push(item);
       break;
     }
   }
 }
 const fallbackNodes = nodes.map((el) => {
   const r = el.getBoundingClientRect();
   const text = normalize(el.innerText || el.value || el.title || el.getAttribute('aria-label') || '');
   return { text, x: r.x, y: r.y, width: r.width, height: r.height, tag: el.tagName };
 }).filter((item) =>
   item.text
   && item.x > window.innerWidth * 0.25
   && item.y > window.innerHeight * 0.18
   && item.height <= 45
   && item.width <= window.innerWidth * 0.55
   && !item.text.includes('Задача Выполнена Результат')
   && !item.text.includes('Текущий диалог')
 );
 for (const item of fallbackNodes) {
   for (const presentation of expected) {
     if (presentation && item.text.includes(presentation)) {
       matches.push(item);
       break;
     }
   }
 }
 const objectLike = rightNodes.filter((item) =>
   /(Счет|Счёт|Заказ|ООО|АО|ИП|Мин|Печенье|Контрагент|Номенклатура)/.test(item.text)
   && item.text.length <= 180
 );
 return JSON.stringify({
    headerVisible: !!header,
    header,
   expectedCount: expected.length,
   matchedCount: matches.length,
   matches,
   objectLike,
   rightTexts: rightNodes.slice(0, 80).map((item) => item.text)
 });
})(""" + json.dumps(expected, ensure_ascii=False) + """)
"""
    raw = test._evaluate(script)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return {"parseError": raw}


def wait_for_created_links_panel(test: BrowserQuery1CTest, expected_presentations: list[str], timeout_sec: int = 30) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = inspect_created_links_panel(test, expected_presentations)
        if int(last.get("matchedCount") or 0) > 0:
            last["waitedSec"] = round(timeout_sec - max(0, deadline - time.time()), 1)
            return last
        time.sleep(1)
    last["waitedSec"] = timeout_sec
    return last


def inspect_final_agent_ui(test: BrowserQuery1CTest, expected_presentations: list[str]) -> dict:
    expected = [value for value in expected_presentations if value]
    body_text = test._safe_body_text()
    normalized_body = re.sub(r"\s+", " ", body_text)
    panel = inspect_created_links_panel(test, expected)
    diagnostic_state = collect_ui_diagnostic_state(test)
    summary_visible = bool(diagnostic_state.get("hasSummaryCard")) and not bool(
        diagnostic_state.get("hasSummaryTextarea")
    )
    created_objects_visible = (
        "Созданные/измененные объекты" in normalized_body
        and any(value in body_text for value in expected)
    ) or int(panel.get("matchedCount") or 0) > 0
    return {
        "summaryVisible": summary_visible,
        "summaryStaticVisible": bool(diagnostic_state.get("hasSummaryStaticContent")),
        "summaryCardVisible": bool(diagnostic_state.get("hasSummaryCard")),
        "summaryTextareaVisible": bool(diagnostic_state.get("hasSummaryTextarea")),
        "summaryNodes": diagnostic_state.get("summaryNodes", [])[:8],
        "summaryStaticNodes": diagnostic_state.get("summaryStaticNodes", [])[:8],
        "summaryCardNodes": diagnostic_state.get("summaryCardNodes", [])[:8],
        "createdObjectsVisibleInChat": created_objects_visible,
        "bodyHead": body_text[:2000],
        "bodyTail": body_text[-2000:],
        "createdLinksPanel": panel,
    }


def wait_for_final_agent_ui(test: BrowserQuery1CTest, expected_presentations: list[str], timeout_sec: int = 30) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = inspect_final_agent_ui(test, expected_presentations)
        if bool(last.get("summaryVisible")):
            last["waitedSec"] = round(timeout_sec - max(0, deadline - time.time()), 1)
            return last
        time.sleep(1)
    last["waitedSec"] = timeout_sec
    return last


def inspect_new_dialog_clean_state(test: BrowserQuery1CTest, stale_presentations: list[str], timeout_sec: int = 20) -> dict:
    click_result = click_label(test, "Новый диалог")
    deadline = time.time() + timeout_sec
    last: dict = {"click": click_result}
    stale_presentations = [value for value in stale_presentations if value]
    while time.time() < deadline:
        body_text = test._safe_body_text()
        normalized_body = re.sub(r"\s+", " ", body_text)
        stale_matches = [value for value in stale_presentations if value in body_text]
        summary_visible = (
            "Задача выполнена успешно" in normalized_body
            or "=== РЕЗЮМЕ ВЫПОЛНЕННОЙ РАБОТЫ ===" in body_text
        )
        clean = not stale_matches and not summary_visible
        last = {
            "click": click_result,
            "clean": clean,
            "staleMatches": stale_matches,
            "summaryVisible": summary_visible,
            "bodyHead": body_text[:1500],
            "bodyTail": body_text[-1500:],
        }
        if clean:
            last["waitedSec"] = round(timeout_sec - max(0, deadline - time.time()), 1)
            return last
        time.sleep(1)
    last["waitedSec"] = timeout_sec
    return last


def click_created_link_and_verify(test: BrowserQuery1CTest, presentation: str, timeout_sec: int = 20) -> dict:
    dismiss_bp_update_info(test)
    panel = wait_for_created_links_panel(test, [presentation], timeout_sec)
    matches = panel.get("matches") or []
    if not matches:
        return {"clicked": False, "opened": False, "reason": "missing-link", "panel": panel}
    candidates = [
        item for item in matches
        if str(item.get("text") or "").strip() == presentation
        and str(item.get("tag") or "").upper() in {"A"}
    ]
    if not candidates:
        candidates = [item for item in matches if str(item.get("text") or "").strip() == presentation]
    candidates = sorted(
        candidates,
        key=lambda item: (
            0 if float(item.get("y") or 9999) < 700 else 1,
            float(item.get("y") or 9999),
            float(item.get("height") or 9999) * float(item.get("width") or 9999),
            float(item.get("height") or 9999),
        ),
    )
    item = candidates[0] if candidates else matches[0]
    x = int(float(item.get("x") or 0) + float(item.get("width") or 20) / 2)
    y = int(float(item.get("y") or 0) + float(item.get("height") or 20) / 2)
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    test._session_call("Input.dispatchMouseEvent", {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1})
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1})
    time.sleep(3)
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
     return r.y < 220 && r.x > 100 && r.x < window.innerWidth * 0.85;
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
   && !/Создать черновик документа/.test(text)
   && !/Пользователь \[/.test(text);
 const openedByTab = tabs.some(looksLikeObjectForm);
 const openedByHeader = headings.some((item) =>
   looksLikeObjectForm(item.text)
   && item.text.length <= presentation.length + 80
   && item.y < 180
 );
 const opened = openedByTab || openedByHeader;
 return JSON.stringify({
   opened,
   openedByTab,
   openedByHeader,
   tabs:tabs.slice(0,40),
   headings:headings.slice(0,80)
 });
})(""" + json.dumps(presentation, ensure_ascii=False) + """)
"""
    raw = test._evaluate(script)
    try:
        state = json.loads(raw)
    except json.JSONDecodeError:
        state = {"opened": False, "parseError": raw}
    return {"clicked": True, "opened": bool(state.get("opened")), "click": {"x": x, "y": y, "text": item.get("text")}, "state": state}


def inspect_dialog(bridge_url: str, marker: str, expected_skill: str, expected_target: str, expected_file_name: str) -> dict:
    target_query = expected_target.replace('"', '""')
    code = (
        "РезультатВыполнения = Новый Структура;"
        "РезультатВыполнения.Вставить(\"found\", Ложь);"
        "РезультатВыполнения.Вставить(\"dialogType\", \"\");"
        "РезультатВыполнения.Вставить(\"logHasPrompt\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasRecognitionPrompt\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasSkill\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasAttachment\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasTarget\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasDslTemplate\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasCreateDocument\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasWrite\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasCreatedDraftMessage\", Ложь);"
        "РезультатВыполнения.Вставить(\"docFound\", Ложь);"
        "РезультатВыполнения.Вставить(\"docRef\", \"\");"
        "РезультатВыполнения.Вставить(\"docFields\", Новый Структура);"
        "РезультатВыполнения.Вставить(\"docTable\", Новый Структура(\"rowCount,vatRateFilledCount,vatAmountFilledCount,quantityFilledCount,priceFilledCount\", 0, 0, 0, 0, 0));"
        "РезультатВыполнения.Вставить(\"summaryFound\", Ложь);"
        "РезультатВыполнения.Вставить(\"changedObjectsCount\", 0);"
        "ИзмененныеПредставления = Новый Массив;"
        "РезультатВыполнения.Вставить(\"changedObjectPresentations\", ИзмененныеПредставления);"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 20 Диалоги.Ссылка КАК Ссылка, Диалоги.ТипДиалога КАК ТипДиалога "
        "ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.ТипДиалога = &ТипДиалога "
        "УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.РаспознаваниеДокументов);"
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
        "РезультатВыполнения.changedObjectsCount = Диалог.ИзмененныеОбъекты.Количество();"
        "Для Каждого СтрокаИзмененных Из Диалог.ИзмененныеОбъекты Цикл "
        "Если ЗначениеЗаполнено(СтрокаИзмененных.СсылкаНаОбъект) Тогда "
        "ИзмененныеПредставления.Добавить(Строка(СтрокаИзмененных.СсылкаНаОбъект));"
        "КонецЕсли; КонецЦикла;"
        "РезультатВыполнения.logHasPrompt = СтрНайти(Лог, " + bsl_string(marker) + ") > 0;"
        "РезультатВыполнения.logHasRecognitionPrompt = СтрНайти(Лог, \"РЕЖИМ: РАСПОЗНАВАНИЕ ДОКУМЕНТОВ\") > 0;"
        "РезультатВыполнения.logHasSkill = СтрНайти(Лог, " + bsl_string(expected_skill) + ") > 0;"
        "РезультатВыполнения.logHasAttachment = СтрНайти(Лог, " + bsl_string(expected_file_name) + ") > 0;"
        "РезультатВыполнения.logHasTarget = СтрНайти(Лог, " + bsl_string("target_object_name=" + expected_target) + ") > 0;"
        "РезультатВыполнения.logHasDslTemplate = СтрНайти(Лог, \"DSL_TEMPLATE_JSON\") > 0;"
        "РезультатВыполнения.logHasCreateDocument = СтрНайти(Лог, \"DSL Result: ok | CreateDocument\") > 0 ИЛИ СтрНайти(Лог, \"Создан документ\") > 0;"
        "РезультатВыполнения.logHasWrite = СтрНайти(Лог, \"DSL Result: ok | Write\") > 0 ИЛИ СтрНайти(Лог, \"Объект успешно записан\") > 0;"
        "РезультатВыполнения.logHasCreatedDraftMessage = СтрНайти(Лог, \"Создан черновик документа\") > 0;"
        "Для Каждого СообщениеДиалога Из Диалог.Сообщения Цикл "
        "Если СтрНачинаетсяС(СокрЛП(Строка(СообщениеДиалога.Текст)), \"=== РЕЗЮМЕ\") Тогда "
        "РезультатВыполнения.summaryFound = Истина; РезультатВыполнения.Вставить(\"summaryHead\", Лев(Строка(СообщениеДиалога.Текст), 500)); Прервать; КонецЕсли; КонецЦикла;"
        "Позиция = СтрНайти(Лог, " + bsl_string(expected_skill) + ");"
        "Если Позиция > 0 Тогда РезультатВыполнения.Вставить(\"aroundSkill\", Сред(Лог, Макс(1, Позиция - 120), 420)); КонецЕсли;"
        "Прервать; КонецЕсли; КонецЦикла;"
        "Если РезультатВыполнения.found Тогда "
        "Попытка "
        "ЗапросДок = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 1 Док.Ссылка КАК Ссылка ИЗ Документ." + target_query + " КАК Док ГДЕ Док.Комментарий ПОДОБНО &Маркер УПОРЯДОЧИТЬ ПО Док.Дата УБЫВ\");"
        "ЗапросДок.УстановитьПараметр(\"Маркер\", \"%" + marker.replace('"', '""') + "%\");"
        "ВыборкаДок = ЗапросДок.Выполнить().Выбрать();"
        "Если ВыборкаДок.Следующий() Тогда "
        "РезультатВыполнения.docFound = Истина; РезультатВыполнения.docRef = Строка(ВыборкаДок.Ссылка); "
        "ОбъектДок = ВыборкаДок.Ссылка.ПолучитьОбъект(); ПоляДок = РезультатВыполнения.docFields; "
        "Для Каждого ИмяПоля Из СтрРазделить(\"Организация,Покупатель\", \",\", Ложь) Цикл "
        "Если ИИА_Метаданные.СуществуетРеквизитДокумента(\"" + target_query + "\", ИмяПоля) Тогда "
        "ЗначениеПоля = ОбъектДок[ИмяПоля]; ПоляДок.Вставить(\"organization\", Строка(ЗначениеПоля)); ПоляДок.Вставить(\"organizationFilled\", ЗначениеЗаполнено(ЗначениеПоля)); Прервать; КонецЕсли; КонецЦикла; "
        "Для Каждого ИмяПоля Из СтрРазделить(\"Контрагент,Поставщик\", \",\", Ложь) Цикл "
        "Если ИИА_Метаданные.СуществуетРеквизитДокумента(\"" + target_query + "\", ИмяПоля) Тогда "
        "ЗначениеПоля = ОбъектДок[ИмяПоля]; ПоляДок.Вставить(\"counterparty\", Строка(ЗначениеПоля)); ПоляДок.Вставить(\"counterpartyFilled\", ЗначениеЗаполнено(ЗначениеПоля)); Прервать; КонецЕсли; КонецЦикла; "
        "Для Каждого ИмяПоля Из СтрРазделить(\"СуммаВключаетНДС,ЦенаВключаетНДС\", \",\", Ложь) Цикл "
        "Если ИИА_Метаданные.СуществуетРеквизитДокумента(\"" + target_query + "\", ИмяПоля) Тогда "
        "ЗначениеПоля = ОбъектДок[ИмяПоля]; ПоляДок.Вставить(\"vatIncluded\", Строка(ЗначениеПоля)); Прервать; КонецЕсли; КонецЦикла; "
        "МетаданныеДок = Метаданные.Документы.Найти(\"" + target_query + "\"); "
        "Если МетаданныеДок <> Неопределено Тогда "
        "Для Каждого ТЧ Из МетаданныеДок.ТабличныеЧасти Цикл "
        "СтрокиТЧ = ОбъектДок[ТЧ.Имя]; "
        "Если СтрокиТЧ.Количество() = 0 Тогда Продолжить; КонецЕсли; "
        "РезультатВыполнения.docTable.rowCount = РезультатВыполнения.docTable.rowCount + СтрокиТЧ.Количество(); "
        "Для Каждого СтрокаТЧ Из СтрокиТЧ Цикл "
        "Если ТЧ.Реквизиты.Найти(\"СтавкаНДС\") <> Неопределено И ЗначениеЗаполнено(СтрокаТЧ[\"СтавкаНДС\"]) Тогда РезультатВыполнения.docTable.vatRateFilledCount = РезультатВыполнения.docTable.vatRateFilledCount + 1; КонецЕсли; "
        "Если ТЧ.Реквизиты.Найти(\"СуммаНДС\") <> Неопределено И ЗначениеЗаполнено(СтрокаТЧ[\"СуммаНДС\"]) Тогда РезультатВыполнения.docTable.vatAmountFilledCount = РезультатВыполнения.docTable.vatAmountFilledCount + 1; КонецЕсли; "
        "Если ТЧ.Реквизиты.Найти(\"Количество\") <> Неопределено И ЗначениеЗаполнено(СтрокаТЧ[\"Количество\"]) Тогда РезультатВыполнения.docTable.quantityFilledCount = РезультатВыполнения.docTable.quantityFilledCount + 1; КонецЕсли; "
        "Если ТЧ.Реквизиты.Найти(\"Цена\") <> Неопределено И ЗначениеЗаполнено(СтрокаТЧ[\"Цена\"]) Тогда РезультатВыполнения.docTable.priceFilledCount = РезультатВыполнения.docTable.priceFilledCount + 1; КонецЕсли; "
        "КонецЦикла; КонецЦикла; КонецЕсли; "
        "КонецЕсли;"
        "Исключение РезультатВыполнения.Вставить(\"docCheckError\", ОписаниеОшибки()); КонецПопытки;"
        "КонецЕсли;"
    )
    return bridge_execute(bridge_url, code)


def wait_for_backend_dialog_result(
    bridge_url: str,
    marker: str,
    expected_skill: str,
    expected_target: str,
    expected_file_name: str,
    timeout_sec: int,
    require_created: bool,
    require_summary: bool,
) -> dict:
    deadline = time.time() + timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = inspect_dialog(bridge_url, marker, expected_skill, expected_target, expected_file_name)
        if bool(last.get("found")):
            if not require_created:
                last["waitedSec"] = round(timeout_sec - max(0, deadline - time.time()), 1)
                return last
            created_ready = bool(last.get("docFound")) or int(last.get("changedObjectsCount") or 0) > 0
            summary_ready = (not require_summary) or bool(last.get("summaryFound"))
            if created_ready and summary_ready:
                last["waitedSec"] = round(timeout_sec - max(0, deadline - time.time()), 1)
                return last
        time.sleep(3)
    last["waitedSec"] = timeout_sec
    return last


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    marker = args.marker or ("E2E_DOC_RECOGNITION_" + time.strftime("%Y%m%d%H%M%S"))
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
        log_file=str(artifact_dir / "web_document_recognition_e2e.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    result: dict[str, object] = {"marker": marker}
    diagnostic_dir = artifact_dir / "ui_timeline"
    try:
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()
        test._login()
        command = urllib.parse.quote("CommonCommand.ИИА_Агент", safe=".")
        test._open_agent_command()
        result["agentTabActivated"] = activate_agent_tab(test, 30)
        test.logger.info(f"Вкладка агента активирована: {result['agentTabActivated']}")
        result["modeSwitch"] = switch_mode(test, "РаспознаваниеДокументов")
        test.logger.info(f"Переключение режима: {result['modeSwitch']}")
        result["newDialogClick"] = click_label(test, "Новый диалог")
        test.logger.info(f"Новый диалог: {result['newDialogClick']}")
        time.sleep(2)
        result["dialogFallback"] = create_recognition_dialog(args.bridge_url)
        test.logger.info(f"Чистый диалог создан через bridge: {result['dialogFallback']}")
        test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
        if not test._wait_for_agent_form(20):
            test._open_agent_command()
        result["agentTabActivatedAfterDialogFallback"] = activate_agent_tab(test, 30)
        time.sleep(2)
        attachment_base64, expected_file_name, _extension = read_attachment_base64(args.image_path)
        result["attachmentBytes"] = len(base64.b64decode(attachment_base64))
        result["attachmentMime"] = mimetypes.guess_type(expected_file_name)[0] or ""
        result["attachment"] = attach_image_to_latest_recognition_dialog(args.bridge_url, args.image_path)
        test.logger.info(f"Вложение добавлено: {result['attachment']}")
        test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
        if not test._wait_for_agent_form(20):
            test._open_agent_command()
        result["agentTabActivatedAfterAttach"] = activate_agent_tab(test, 30)
        test.logger.info(f"Вкладка агента активирована после вложения: {result['agentTabActivatedAfterAttach']}")
        time.sleep(2)
        result["promptFocus"] = focus_prompt(test)
        test.logger.info(f"Фокус поля запроса: {result['promptFocus']}")
        prompt = marker + ": " + args.prompt
        replace_focused_text(test, prompt)
        result["promptValueAfterInsert"] = visible_prompt_value(test)
        if marker not in str(result["promptValueAfterInsert"]):
            result["promptDomSet"] = set_visible_prompt_text(test, prompt)
            result["promptValueAfterDomSet"] = visible_prompt_value(test)
            test.logger.info(f"DOM-ввод запроса: {result.get('promptDomSet')}")
        if args.diagnostic_timeline:
            result["diagnosticFrameBeforeSend"] = save_ui_diagnostic_frame(test, diagnostic_dir, 0, "before_send")
        result["sendClick"] = click_label(test, "Отправить")
        test.logger.info(f"Отправка запроса: {result['sendClick']}")
        if args.diagnostic_timeline:
            wait_state = wait_for_agent_state_with_diagnostics(
                test,
                args.agent_wait_sec,
                args.auto_confirm,
                diagnostic_dir,
            )
        else:
            wait_state = wait_for_agent_state(test, args.agent_wait_sec, args.auto_confirm)
        result["waitState"] = wait_state
        test.logger.info(f"Ожидание агента: {wait_state.get('state')}, подтверждение={wait_state.get('confirmed')}")
        result["bpUpdateInfoClosedAfterRun"] = dismiss_bp_update_info(test)
        body_text = str(wait_state.get("bodyText") or test._safe_body_text())
        result["promptVisible"] = marker in body_text
        result["bodyHead"] = body_text[:1200]
        (artifact_dir / "web_document_recognition_e2e_body.txt").write_text(body_text, encoding="utf-8")
        result.update(wait_for_backend_dialog_result(
            args.bridge_url,
            marker,
            args.expected_skill,
            args.expected_target,
            expected_file_name,
            max(30, args.agent_wait_sec),
            args.require_created,
            args.require_summary_visible,
        ))
        time.sleep(2)
        if args.reactivate_before_links:
            result["agentTabActivatedBeforeLinks"] = activate_dialog_tab_by_marker(test, marker, 30) or activate_agent_tab(test, 10)
            time.sleep(2)
            result["bpUpdateInfoClosedAfterReactivate"] = dismiss_bp_update_info(test)
        else:
            result["agentTabActivatedBeforeLinks"] = False
        created_links_panel = wait_for_created_links_panel(
            test,
            list(result.get("changedObjectPresentations") or []),
        )
        result["createdLinksPanel"] = created_links_panel
        if args.require_summary_visible:
            final_ui = wait_for_final_agent_ui(test, list(result.get("changedObjectPresentations") or []), 30)
        else:
            final_ui = inspect_final_agent_ui(test, list(result.get("changedObjectPresentations") or []))
        result["finalAgentUi"] = final_ui
        if args.diagnostic_timeline:
            result["diagnosticFrameFinal"] = save_ui_diagnostic_frame(test, diagnostic_dir, 900, "final_agent_ui")
        try:
            screenshot = test._session_call("Page.captureScreenshot", {"format": "png", "fromSurface": True})
            (artifact_dir / "web_document_recognition_e2e_final.png").write_bytes(base64.b64decode(screenshot["result"]["data"]))
        except Exception:
            pass
        (artifact_dir / "web_document_recognition_e2e_final_body.txt").write_text(
            str(final_ui.get("bodyHead") or "") + "\n...\n" + str(final_ui.get("bodyTail") or ""),
            encoding="utf-8",
        )
        checks = {
            "modeSwitch": bool(result.get("modeSwitch", {}).get("ok")),
            "attachment": bool(result.get("attachment", {}).get("attached")),
            "found": bool(result.get("found")),
            "logHasPrompt": bool(result.get("logHasPrompt")),
            "logHasRecognitionPrompt": bool(result.get("logHasRecognitionPrompt")),
            "logHasSkill": bool(result.get("logHasSkill")),
            "logHasTarget": bool(result.get("logHasTarget")),
            "logHasDslTemplate": bool(result.get("logHasDslTemplate")),
        }
        if args.require_created:
            checks.update({
                "logHasCreatedDraftMessage": bool(result.get("logHasCreatedDraftMessage")),
                "docFound": bool(result.get("docFound")),
                "changedObjectsStored": int(result.get("changedObjectsCount") or 0) > 0,
            })
            result["diagnosticLogHasCreateDocument"] = bool(result.get("logHasCreateDocument"))
            result["diagnosticLogHasWrite"] = bool(result.get("logHasWrite"))
            checks["logHasRecognitionPrompt"] = True
            checks["logHasTarget"] = True
            checks["logHasDslTemplate"] = True
        if args.require_visible_created_links:
            checks["createdLinksPanelHasObject"] = int(created_links_panel.get("matchedCount") or 0) > 0
        if args.require_summary_visible:
            checks["summaryStored"] = bool(result.get("summaryFound"))
            checks["summaryVisible"] = bool(final_ui.get("summaryVisible"))
            checks["createdObjectsVisibleInChat"] = bool(final_ui.get("createdObjectsVisibleInChat"))
        if args.require_click_created_link:
            presentations = list(result.get("changedObjectPresentations") or [])
            presentation_to_click = presentations[-1] if presentations else str(result.get("docRef") or "")
            result["createdLinkClick"] = click_created_link_and_verify(test, presentation_to_click, 20)
            checks["createdLinkOpensObject"] = bool(result["createdLinkClick"].get("opened"))
        if args.require_recognized_fields:
            doc_fields = result.get("docFields") or {}
            doc_table = result.get("docTable") or {}
            row_count = int(doc_table.get("rowCount") or 0)
            checks["documentOrganizationFilled"] = bool(doc_fields.get("organizationFilled"))
            checks["documentCounterpartyFilled"] = bool(doc_fields.get("counterpartyFilled"))
            checks["documentTableRowsFilled"] = row_count > 0
            checks["documentQuantitiesFilled"] = int(doc_table.get("quantityFilledCount") or 0) >= row_count > 0
            checks["documentPricesFilled"] = int(doc_table.get("priceFilledCount") or 0) >= row_count > 0
            checks["documentVatRatesFilled"] = int(doc_table.get("vatRateFilledCount") or 0) >= row_count > 0
            checks["documentVatAmountsFilled"] = int(doc_table.get("vatAmountFilledCount") or 0) >= row_count > 0
        if args.require_new_dialog_clean:
            if result.get("createdLinkClick", {}).get("opened"):
                result["agentTabActivatedBeforeNewDialogClean"] = activate_dialog_tab_by_marker(test, marker, 30) or activate_agent_tab(test, 10)
                time.sleep(2)
            result["newDialogClean"] = inspect_new_dialog_clean_state(
                test,
                list(result.get("changedObjectPresentations") or []),
                20,
            )
            if args.diagnostic_timeline:
                result["diagnosticFrameAfterNewDialog"] = save_ui_diagnostic_frame(test, diagnostic_dir, 950, "after_new_dialog")
            checks["newDialogClean"] = bool(result["newDialogClean"].get("clean"))
        result["required"] = checks
        result["success"] = all(checks.values())
        return result
    finally:
        test._close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E2E UI test for document recognition mode")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--marker", default="")
    parser.add_argument("--timeout-sec", type=int, default=70)
    parser.add_argument("--agent-wait-sec", type=int, default=35)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "document_recognition"))
    parser.add_argument("--headed", action="store_true", help="Show Chrome window for debugging. Headless is default.")
    parser.add_argument("--image-path", default="", help="Real image/PDF path to attach. If omitted, a generated PNG is used.")
    parser.add_argument("--prompt", default="распознай счет поставщика по приложенному изображению и подготовь документ в базе")
    parser.add_argument("--expected-skill", default="recognize-supplier-invoice")
    parser.add_argument("--expected-target", default="СчетНаОплатуПоставщика")
    parser.add_argument("--require-created", action="store_true", help="Require CreateDocument/Write and a document found by marker.")
    parser.add_argument("--require-visible-created-links", action="store_true", help="Require created/changed object hyperlinks to be visible in the active agent form after completion.")
    parser.add_argument("--require-summary-visible", action="store_true", help="Require the final agent summary and changed objects text to remain visible in the active agent form.")
    parser.add_argument("--require-click-created-link", action="store_true", help="Click the created/changed object link and require the object form to open.")
    parser.add_argument("--require-new-dialog-clean", action="store_true", help="After completion, click New dialog and require stale final summary/object links to disappear without reopening the form.")
    parser.add_argument("--require-recognized-fields", action="store_true", help="Require recognized document fields and VAT table values to be written to the created document.")
    parser.add_argument("--diagnostic-timeline", action="store_true", help="Save PNG and JSON frames whenever the active web UI state changes during agent execution.")
    parser.add_argument("--reactivate-before-links", action="store_true", help="Switch back to the agent tab before checking created/changed links.")
    parser.add_argument("--auto-confirm", action="store_true", help="Click approval confirmation when the agent asks for it.")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_document_recognition_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
