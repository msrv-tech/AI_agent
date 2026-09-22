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


def mouse_click(test: BrowserQuery1CTest, x: float, y: float) -> None:
    x = float(x)
    y = float(y)
    test._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
    test._session_call(
        "Input.dispatchMouseEvent",
        {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
    )
    test._session_call(
        "Input.dispatchMouseEvent",
        {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
    )


def find_text_boxes(test: BrowserQuery1CTest, text: str) -> list[dict]:
    raw = test._evaluate(
        """
JSON.stringify((() => {
  const needle = %s;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const out = [];
  let node;
  while (node = walker.nextNode()) {
    const t = (node.nodeValue || '').trim();
    if (t !== needle) continue;
    const el = node.parentElement;
    if (!el) continue;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    if (r.width < 4 || r.height < 4 || s.display === 'none' || s.visibility === 'hidden') continue;
    out.push({t, x: r.x, y: r.y, w: r.width, h: r.height});
  }
  return out;
})())
"""
        % json.dumps(text, ensure_ascii=False)
    )
    try:
        parsed = json.loads(raw) if raw else []
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []


def click_text_cdp(test: BrowserQuery1CTest, label: str) -> str:
    boxes = find_text_boxes(test, label)
    if not boxes:
        return click_label(test, label)
    visible = [item for item in boxes if item.get("y", 0) > 30] or boxes
    visible.sort(key=lambda item: float(item.get("w", 0)) * float(item.get("h", 0)))
    box = visible[0]
    mouse_click(test, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    return f"cdp:{round(box['x'])},{round(box['y'])}"


def read_agent_surface_text(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
(() => {
  const prompt = document.querySelector('[id$="_ТекущийТекст_i0"]');
  let root = prompt;
  while (root && root.parentElement) {
    root = root.parentElement;
    if (/^form\\d+$/.test(root.id || '')) break;
  }
  const status = Array.from(document.querySelectorAll('[id*="СтрокаСтатуса"]'))
    .map((el) => el.innerText || el.textContent || el.value || '')
    .filter(Boolean);
  const areas = Array.from(document.querySelectorAll('textarea'))
    .filter((el) => !(el.id || '').includes('ТекущийТекст'))
    .map((el) => el.value || '')
    .filter(Boolean);
  const formText = root && root !== document.body ? (root.innerText || '') : '';
  return status.concat(areas, [formText]).join('\\n');
})()
"""
    )


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


def press_key(test: BrowserQuery1CTest, key_code: int, key: str, code: str, modifiers: int = 0) -> None:
    payload = {
        "windowsVirtualKeyCode": key_code,
        "nativeVirtualKeyCode": key_code,
        "key": key,
        "code": code,
        "modifiers": modifiers,
    }
    test._session_call("Input.dispatchKeyEvent", {"type": "rawKeyDown", **payload})
    test._session_call("Input.dispatchKeyEvent", {"type": "keyUp", **payload})


def press_shift_tab(test: BrowserQuery1CTest) -> None:
    test._session_call(
        "Input.dispatchKeyEvent",
        {
            "type": "rawKeyDown",
            "windowsVirtualKeyCode": 16,
            "nativeVirtualKeyCode": 16,
            "key": "Shift",
            "code": "ShiftLeft",
            "modifiers": 8,
        },
    )
    press_key(test, 9, "Tab", "Tab", modifiers=8)
    test._session_call(
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "windowsVirtualKeyCode": 16,
            "nativeVirtualKeyCode": 16,
            "key": "Shift",
            "code": "ShiftLeft",
        },
    )


def describe_agent_inputs(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
JSON.stringify((() => {
  const vis = (e) => {
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return r.width > 8 && r.height > 8 && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const items = Array.from(document.querySelectorAll('textarea, input, [id$="_ТекущийТекст"], [id$="_ТекущийТекст_i0"]'))
    .filter(vis)
    .slice(0, 20)
    .map((e) => {
      const r = e.getBoundingClientRect();
      const hx = r.x + Math.min(40, r.width / 2);
      const hy = r.y + Math.min(16, r.height / 2);
      const top = document.elementFromPoint(hx, hy);
      return {
        tag: e.tagName,
        id: e.id,
        x: Math.round(r.x),
        y: Math.round(r.y),
        w: Math.round(r.width),
        h: Math.round(r.height),
        hit: top ? (top.tagName + ':' + (top.id || '')) : 'none',
        val: String(e.value || '').slice(0, 40)
      };
    });
  const dd = document.getElementById('editDropDown');
  const ae = document.activeElement;
  return {
    active: ae ? (ae.tagName + ':' + (ae.id || '')) : 'none',
    dropdown: !!(dd && dd.offsetWidth),
    items
  };
})())
"""
    )


def press_ctrl_key(test: BrowserQuery1CTest, key_code: int, commands: list[str] | None = None) -> None:
    key = "v" if key_code == 86 else "a"
    code = "KeyV" if key_code == 86 else "KeyA"
    test._session_call(
        "Input.dispatchKeyEvent",
        {
            "type": "rawKeyDown",
            "windowsVirtualKeyCode": 17,
            "nativeVirtualKeyCode": 17,
            "modifiers": 2,
            "key": "Control",
            "code": "ControlLeft",
        },
    )
    payload = {
        "type": "rawKeyDown",
        "windowsVirtualKeyCode": key_code,
        "nativeVirtualKeyCode": key_code,
        "modifiers": 2,
        "key": key,
        "code": code,
    }
    if commands:
        payload["commands"] = commands
    test._session_call("Input.dispatchKeyEvent", payload)
    test._session_call(
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "windowsVirtualKeyCode": key_code,
            "nativeVirtualKeyCode": key_code,
            "modifiers": 2,
            "key": key,
            "code": code,
        },
    )
    test._session_call(
        "Input.dispatchKeyEvent",
        {
            "type": "keyUp",
            "windowsVirtualKeyCode": 17,
            "nativeVirtualKeyCode": 17,
            "key": "Control",
            "code": "ControlLeft",
        },
    )


def write_clipboard(test: BrowserQuery1CTest, text: str) -> str:
    href = test._current_url() or test.config.web_url
    parsed = urllib.parse.urlparse(href)
    origin = f"{parsed.scheme}://{parsed.netloc}" if parsed.scheme and parsed.netloc else href
    grant = test._browser_call(
        "Browser.grantPermissions",
        {
            "origin": origin,
            "permissions": ["clipboardReadWrite", "clipboardSanitizedWrite"],
        },
    )
    if grant.get("error"):
        raise RuntimeError(f"Browser.grantPermissions: {grant['error']}")
    expr = "navigator.clipboard.writeText(%s).then(() => 'ok')" % json.dumps(text, ensure_ascii=False)
    result = test._session_call(
        "Runtime.evaluate",
        {"expression": expr, "awaitPromise": True, "returnByValue": True},
    )
    payload = result.get("result") or {}
    if result.get("error"):
        raise RuntimeError(f"clipboard.writeText CDP: {result['error']}")
    if payload.get("exceptionDetails"):
        raise RuntimeError(f"clipboard.writeText: {payload['exceptionDetails']}")
    value = str((payload.get("result") or {}).get("value", ""))
    if value != "ok":
        raise RuntimeError(f"clipboard.writeText вернул {value!r}")
    return origin


def click_id_suffix(test: BrowserQuery1CTest, suffix: str) -> str:
    raw = test._evaluate(
        """
(() => {
  const items = Array.from(document.querySelectorAll(%s)).map((e) => {
    e.scrollIntoView({block:'nearest'});
    const r = e.getBoundingClientRect();
    const s = getComputedStyle(e);
    return {
      id: e.id || '',
      x: r.x, y: r.y, w: r.width, h: r.height,
      visible: r.width > 4 && r.height > 4 && r.x > -1000 && r.y > -1000
        && s.display !== 'none' && s.visibility !== 'hidden'
    };
  }).filter((item) => item.visible);
  items.sort((a, b) => (b.w * b.h) - (a.w * a.h));
  return items.length ? JSON.stringify(items[0]) : 'missing';
})()
"""
        % json.dumps(f'[id$="{suffix}"]')
    )
    if not raw or raw == "missing":
        return "missing"
    try:
        box = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Не разобрать координаты {suffix}: {raw!r}") from exc
    mouse_click(test, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    return f"id:{box.get('id')}"


def prompt_field_value(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
(() => {
  const e = document.querySelector('[id$="_ТекущийТекст_i0"]');
  if (!e) return '__missing__';
  return String(e.value || '');
})()
"""
    )


def focused_element_info(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
(() => {
  const e = document.activeElement;
  if (!e) return 'none';
  return [e.tagName, e.id || '', String(e.value || '').slice(0, 80)].join(':');
})()
"""
    )


def focus_by_id_suffix(test: BrowserQuery1CTest, suffix: str) -> str:
    raw = test._evaluate(
        """
(() => {
  const e = document.querySelector(%s);
  if (!e) return 'missing';
  e.scrollIntoView({block:'center'});
  const r = e.getBoundingClientRect();
  return JSON.stringify({id:e.id||'', x:r.x, y:r.y, w:r.width, h:r.height});
})()
"""
        % json.dumps(f'[id$="{suffix}"]')
    )
    if not raw or raw == "missing":
        return "missing"
    try:
        box = json.loads(raw)
    except json.JSONDecodeError:
        return raw
    if box.get("w", 0) > 4:
        mouse_click(test, box["x"] + box["w"] / 2, box["y"] + min(box["h"] / 2, 20))
        time.sleep(0.2)
    return f"id:{box.get('id')}"


def click_prompt_inset(test: BrowserQuery1CTest) -> str:
    raw = test._evaluate(
        r"""
(() => {
  const e = document.querySelector('[id$="_ТекущийТекст_i0"]');
  if (!e) return 'missing';
  e.scrollIntoView({block:'nearest'});
  const r = e.getBoundingClientRect();
  return JSON.stringify({id:e.id||'', x:r.x, y:r.y, w:r.width, h:r.height});
})()
"""
    )
    if not raw or raw == "missing":
        return "missing"
    box = json.loads(raw)
    mouse_click(
        test,
        float(box["x"]) + min(64.0, float(box["w"]) * 0.15),
        float(box["y"]) + min(28.0, float(box["h"]) * 0.3),
    )
    time.sleep(0.2)
    return f"inset:{box.get('id')}"


def focus_prompt(test: BrowserQuery1CTest) -> str:
    inset = click_prompt_inset(test)
    info = focused_element_info(test)
    if "ТекущийТекст" in (info or "") and "TEXTAREA" in (info or ""):
        return f"inset:{inset};active:{info}"
    wrapper = click_id_suffix(test, "_ТекущийТекст")
    time.sleep(0.25)
    info = focused_element_info(test)
    if "ТекущийТекст" in (info or "") and "TEXTAREA" in (info or ""):
        return f"wrapper:{wrapper};active:{info}"
    inner = focus_by_id_suffix(test, "_ТекущийТекст_i0")
    time.sleep(0.2)
    info = focused_element_info(test)
    if "ТекущийТекст" in (info or ""):
        return f"inner:{inner};active:{info}"
    script = r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 let items=Array.from(document.querySelectorAll('textarea')).filter(visible)
  .sort((a,b)=>{
    const ra=a.getBoundingClientRect(), rb=b.getBoundingClientRect();
    return (rb.width*rb.height)-(ra.width*ra.height);
  });
 if(!items.length) return 'missing';
 const e=items[0];
 e.scrollIntoView({block:'center'});
 const r=e.getBoundingClientRect();
 return JSON.stringify({id:e.id||'', x:r.x, y:r.y, w:r.width, h:r.height});
})()
"""
    raw = test._evaluate(script)
    if raw and raw != "missing":
        try:
            box = json.loads(raw)
            mouse_click(test, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
            time.sleep(0.2)
            return f"largest:{box.get('id')};active:{focused_element_info(test)}"
        except json.JSONDecodeError:
            pass
    return f"unfocused:{info};raw:{raw}"


def replace_focused_text(test: BrowserQuery1CTest, text: str) -> None:
    write_clipboard(test, text)
    press_ctrl_key(test, 65, ["selectAll"])
    time.sleep(0.15)
    press_ctrl_key(test, 86, ["paste"])
    time.sleep(0.4)


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
            skip_query1c_prepare=True,
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
