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
    click_id_suffix,
    click_label,
    click_prompt_inset,
    click_text_cdp,
    describe_agent_inputs,
    find_text_boxes,
    focus_by_id_suffix,
    focus_prompt,
    focused_element_info,
    install_fixture_skill,
    mouse_click,
    press_key,
    press_shift_tab,
    prompt_field_value,
    read_agent_surface_text,
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


def wait_body_contains(test: BrowserQuery1CTest, needles: list[str], timeout_sec: float) -> str:
    deadline = time.time() + timeout_sec
    last = ""
    while time.time() < deadline:
        last = test._safe_body_text()
        if any(needle in last for needle in needles):
            return last
        time.sleep(0.4)
    return last


def current_mode_value(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
(()=>{
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>40&&r.height>15&&r.x>-1000&&r.y>-1000&&s.display!=='none'&&s.visibility!=='hidden'};
 const items=Array.from(document.querySelectorAll('input')).filter(visible).filter(e=>(e.value||'').includes('Агент') || (e.value||'').includes('Запрос1С'));
 return items.length ? items[0].value : '';
})()
"""
    )


def switch_mode(test: BrowserQuery1CTest, mode: str) -> dict:
    before = current_mode_value(test)
    focused = focus_by_id_suffix(test, "_ТекущийТипСообщения_i0")
    if focused == "missing":
        focused = focus_mode_field(test)
    replace_focused_text(test, mode)
    press_enter(test)
    time.sleep(1)
    after = current_mode_value(test)
    if mode not in (after or ""):
        replace_focused_text(test, mode)
        press_enter(test)
        time.sleep(1)
        after = current_mode_value(test)
    press_key(test, 27, "Escape", "Escape")
    time.sleep(0.3)
    after_escape = ensure_agent_form(test)
    return {"before": before, "after": after, "focused": focused, "ensure": after_escape}


def agent_status_text(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
(() => {
  const els = Array.from(document.querySelectorAll('[id*="СтрокаСтатуса"]'));
  return els.map((el) => el.innerText || el.textContent || el.value || '').join(' | ');
})()
"""
    )


def current_dialog_title(test: BrowserQuery1CTest) -> str:
    return test._evaluate(
        r"""
(() => {
  const e = document.querySelector('[id$="_ТекущийДиалог_i0"]');
  return e ? String(e.value || '') : '';
})()
"""
    )


def click_topmost_text(test: BrowserQuery1CTest, label: str) -> str:
    boxes = find_text_boxes(test, label)
    if not boxes:
        return "missing"
    boxes.sort(key=lambda item: float(item.get("y", 9999)))
    box = boxes[0]
    mouse_click(test, box["x"] + box["w"] / 2, box["y"] + box["h"] / 2)
    return f"top:{round(box['x'])},{round(box['y'])}"


def chat_is_reset(surface: str, status: str, dialog_title: str, previous_title: str) -> bool:
    idle = "Создан новый диалог" in (status or "") or "Готов к работе" in (status or "")
    new_catalog_item = "Диалог ИИ от" in (dialog_title or "")
    title_changed = bool(dialog_title) and dialog_title != previous_title
    leftover_chat = "Пользователь [" in (surface or "") or "Система [" in (surface or "")
    return idle and new_catalog_item and title_changed and not leftover_chat


def confirmation_pending(test: BrowserQuery1CTest) -> bool:
    status = agent_status_text(test) or ""
    if any(
        marker in status
        for marker in (
            "Ожидает подтверждения",
            "Ожидает решения",
            "Требуется подтверждение",
        )
    ):
        return True
    surface = read_agent_surface_text(test) or ""
    if "Открыть подтверждение" in surface or "Ожидает решения в отдельном окне" in surface:
        return True
    body = test._safe_body_text()
    return "Подтверждение действия" in body and bool(find_text_boxes(test, "Выполнить"))


def confirm_pending_action(test: BrowserQuery1CTest, timeout_sec: float = 15) -> dict:
    """Approve the on-form / modal confirmation. Raise if the pending state stays."""
    result: dict[str, object] = {"clicks": []}
    modal_ready = bool(find_text_boxes(test, "Выполнить"))
    pending = confirmation_pending(test)
    if not pending and not modal_ready:
        result["needed"] = False
        return result
    result["needed"] = True
    if not modal_ready:
        opened = click_id_suffix(test, "_ПодтвердитьДействие")
        if opened == "missing":
            opened = click_topmost_text(test, "Открыть подтверждение")
        if opened == "missing":
            opened = click_topmost_text(test, "Подтвердить")
        result["clicks"].append(opened)
        if opened == "missing":
            raise RuntimeError(
                "Нужно подтверждение, но нет кнопки «Открыть подтверждение»/«Подтвердить»: "
                + agent_status_text(test)
            )
        deadline_open = time.time() + 8
        while time.time() < deadline_open and not find_text_boxes(test, "Выполнить"):
            time.sleep(0.3)
    approve = click_id_suffix(test, "_Выполнить")
    if approve == "missing":
        approve = click_topmost_text(test, "Выполнить")
    result["clicks"].append(approve)
    if approve == "missing":
        raise RuntimeError(
            "Окно «Подтверждение действия» не показало кнопку «Выполнить». clicks="
            + str(result["clicks"])
        )
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        if not confirmation_pending(test):
            result["confirmed"] = True
            result["afterStatus"] = agent_status_text(test)
            return result
        time.sleep(0.4)
    raise RuntimeError(
        "После «Выполнить» статус подтверждения не снялся: " + agent_status_text(test)
    )


def new_dialog_visible(test: BrowserQuery1CTest) -> bool:
    return bool(inspect_agent_form(test).get("newDialogReady"))


def inspect_agent_form(test: BrowserQuery1CTest) -> dict:
    raw = test._evaluate(
        r"""
(() => {
  const onScreen = (el, minW, minH) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > minW && r.height > minH
      && r.x > -50 && r.y > -50
      && r.x < window.innerWidth && r.y < window.innerHeight
      && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const prompt = document.querySelector('[id$="_ТекущийТекст_i0"]')
    || document.querySelector('[id$="_ТекущийТекст"]');
  const newDialog = document.querySelector('[id$="_НовыйДиалог"]');
  const promptReady = onScreen(prompt, 40, 15);
  const newDialogReady = onScreen(newDialog, 8, 8);
  const sheets = Array.from(document.querySelectorAll('[id*="SpreadsheetDocument"]'))
    .filter((el) => onScreen(el, 80, 80))
    .map((el) => {
      const r = el.getBoundingClientRect();
      return {id: el.id || '', x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height)};
    });
  const active = document.activeElement;
  const activeId = active ? (active.id || '') : '';
  let overlayId = sheets[0] ? sheets[0].id : '';
  if (!overlayId && activeId.includes('SpreadsheetDocument')) overlayId = activeId;
  if (!overlayId && /КартинкаНачальныеостатки|НачальнаяСтраница|StartPage/.test(activeId)) overlayId = activeId;
  if (promptReady) {
    const r = prompt.getBoundingClientRect();
    const cx = r.x + Math.min(64, r.width * 0.15);
    const cy = r.y + Math.min(28, r.height * 0.3);
    const topEl = document.elementFromPoint(cx, cy);
    if (topEl && !prompt.contains(topEl) && !topEl.closest('[id*="ТекущийТекст"]')) {
      const promptForm = prompt.closest('[id^="form"]');
      const topForm = topEl.closest('[id^="form"]');
      if (!promptForm || !topForm || promptForm !== topForm) {
        overlayId = overlayId || topEl.id || (topForm && topForm.id) || topEl.tagName;
      }
    }
  }
  return JSON.stringify({
    promptReady,
    newDialogReady,
    overlayId,
    overlay: overlayId ? {id: overlayId} : null,
    activeId,
    ready: promptReady && newDialogReady && !overlayId
  });
})()
"""
    )
    if not raw:
        return {"ready": False, "overlayId": "", "promptReady": False, "newDialogReady": False}
    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Не разобрать состояние формы агента: {raw!r}") from exc


def agent_form_ready(test: BrowserQuery1CTest) -> bool:
    return bool(inspect_agent_form(test).get("ready"))


def click_overlay_close(test: BrowserQuery1CTest) -> str:
    raw = test._evaluate(
        r"""
(() => {
  const visible = (el) => {
    if (!el) return false;
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 6 && r.height > 6 && r.x > -50 && r.y > -50
      && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const box = (el) => {
    const r = el.getBoundingClientRect();
    return {id: el.id || '', title: el.title || el.getAttribute('aria-label') || '', x: r.x, y: r.y, w: r.width, h: r.height};
  };
  const titled = Array.from(document.querySelectorAll('[title*="Закрыть"], [aria-label*="Закрыть"]'))
    .filter(visible)
    .map(box);
  if (titled.length) {
    titled.sort((a, b) => a.y - b.y || (a.w * a.h) - (b.w * b.h));
    return JSON.stringify({kind: 'title', ...titled[0]});
  }
  const tabs = Array.from(document.querySelectorAll('.openedItem, .openlistItem')).filter(visible);
  const tableTab = tabs.find((el) => /Таблица результатов|Табличный документ/.test(el.innerText || el.title || ''));
  if (tableTab) {
    const r = tableTab.getBoundingClientRect();
    return JSON.stringify({kind: 'table-tab', id: tableTab.id || '', x: r.x + r.width - 10, y: r.y + r.height / 2, w: 12, h: 12});
  }
  return 'missing';
})()
"""
    )
    if not raw or raw == "missing":
        return "missing"
    try:
        box = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Не разобрать кнопку закрытия оверлея: {raw!r}") from exc
    mouse_click(test, float(box["x"]) + float(box.get("w", 8)) / 2, float(box["y"]) + float(box.get("h", 8)) / 2)
    return f"{box.get('kind')}:{box.get('id') or ''}"


def close_foreign_form(test: BrowserQuery1CTest) -> list[str]:
    actions: list[str] = []
    state = inspect_agent_form(test)
    if state.get("ready"):
        return actions
    press_key(test, 27, "Escape", "Escape")
    actions.append("escape")
    time.sleep(0.4)
    state = inspect_agent_form(test)
    if state.get("ready"):
        return actions
    closed = click_overlay_close(test)
    actions.append(f"close:{closed}")
    time.sleep(0.5)
    state = inspect_agent_form(test)
    if state.get("ready"):
        return actions
    overlay_id = str(state.get("overlayId") or "")
    if "SpreadsheetDocument" in overlay_id:
        press_key(test, 115, "F4", "F4", modifiers=2)
        actions.append("ctrl-f4")
        time.sleep(0.5)
        state = inspect_agent_form(test)
        if state.get("ready"):
            return actions
    from automation.ui.web_document_recognition_e2e import activate_agent_tab

    tab = activate_agent_tab(test, 4)
    actions.append(f"tab:{tab}")
    time.sleep(0.4)
    return actions


def ensure_agent_form(test: BrowserQuery1CTest, raise_if_missing: bool = True) -> str:
    if agent_form_ready(test):
        return "already"
    actions = close_foreign_form(test)
    if agent_form_ready(test):
        return "closed-overlay:" + ",".join(actions)
    for _ in range(3):
        press_key(test, 27, "Escape", "Escape")
        time.sleep(0.5)
        if agent_form_ready(test):
            return "escape"
    test._open_agent_command()
    time.sleep(0.8)
    if agent_form_ready(test):
        return "reopened"
    state = inspect_agent_form(test)
    message = (
        "Форма ИИ Агент перекрыта посторонним окном и не вернулась: "
        + json.dumps({"actions": actions, "state": state}, ensure_ascii=False)
    )
    if raise_if_missing:
        raise RuntimeError(message)
    return "failed:" + message


def reset_chat(test: BrowserQuery1CTest, timeout_sec: float = 12) -> dict:
    """Create a fresh ИИ Агент dialog and fail if the previous chat stays on screen."""
    ensure = ensure_agent_form(test)
    before_title = current_dialog_title(test)
    before_status = agent_status_text(test)
    result = {
        "ensure": ensure,
        "beforeDialog": before_title,
        "beforeStatus": (before_status or "")[:160],
        "clicks": [],
    }
    if confirmation_pending(test) or find_text_boxes(test, "Выполнить"):
        result["confirm"] = confirm_pending_action(test)
        before_title = current_dialog_title(test)
        before_status = agent_status_text(test)
        result["beforeDialog"] = before_title
        result["beforeStatus"] = (before_status or "")[:160]
    if "Остановить" in (before_status or "") or "Выполняю" in (before_status or ""):
        stop_click = click_id_suffix(test, "_Отправить")
        if stop_click == "missing":
            stop_click = click_text_cdp(test, "Остановить")
        result["stopClick"] = stop_click
        time.sleep(1.5)
    clicks = [
        click_id_suffix(test, "_НовыйДиалог"),
        click_topmost_text(test, "Новый диалог"),
    ]
    result["clicks"] = clicks
    if all(click == "missing" for click in clicks):
        raise RuntimeError("Кнопка «Новый диалог» не найдена на форме ИИ Агент.")
    if not agent_form_ready(test):
        result["afterClickRecover"] = ensure_agent_form(test)
    deadline = time.time() + timeout_sec
    last_surface = ""
    last_status = ""
    last_title = ""
    while time.time() < deadline:
        last_title = current_dialog_title(test)
        last_status = agent_status_text(test)
        last_surface = read_agent_surface_text(test)
        if chat_is_reset(last_surface, last_status, last_title, before_title):
            result.update(
                {
                    "afterDialog": last_title,
                    "afterStatus": (last_status or "")[:160],
                    "reset": True,
                }
            )
            return result
        time.sleep(0.4)
    raise RuntimeError(
        "Чат не сбросился после «Новый диалог»: "
        + json.dumps(
            {
                "beforeDialog": before_title,
                "afterDialog": last_title,
                "beforeStatus": (before_status or "")[:160],
                "afterStatus": (last_status or "")[:160],
                "clicks": clicks,
                "hasPlaceholder": "Опишите задачу" in last_surface,
                "hasUserBubble": "Пользователь [" in last_surface,
                "surface": last_surface[:400],
            },
            ensure_ascii=False,
        )
    )


def prompt_started(before: str, after: str, prompt: str) -> bool:
    marker = (prompt or "").strip()[:40]
    if "Отправка сообщения" in after:
        return True
    if "Выполняю" in after and "Выполняю" not in before:
        return True
    if "Остановить" in after and "Остановить" not in before:
        return True
    if marker and marker in after and "Готов к работе" not in after:
        return True
    return False


def send_prompt(test: BrowserQuery1CTest, prompt: str, reset: bool = True) -> dict:
    result: dict[str, object] = {}
    if reset:
        result["reset"] = reset_chat(test)
    result["ensure"] = ensure_agent_form(test)
    press_key(test, 27, "Escape", "Escape")
    time.sleep(0.3)
    result["ensureAfterEsc"] = ensure_agent_form(test)
    marker = (prompt or "").strip()[:40]
    for attempt in range(3):
        before = test._safe_body_text()
        result["promptFocus"] = focus_prompt(test)
        result["activeBeforePaste"] = focused_element_info(test)
        if "ТекущийТекст" not in (result["activeBeforePaste"] or ""):
            press_key(test, 27, "Escape", "Escape")
            time.sleep(0.2)
            result["promptInset"] = click_prompt_inset(test)
            result["activeBeforePaste"] = focused_element_info(test)
        if "ТекущийТекст" not in (result["activeBeforePaste"] or ""):
            press_shift_tab(test)
            time.sleep(0.25)
            result["activeAfterShiftTab"] = focused_element_info(test)
            result["activeBeforePaste"] = result["activeAfterShiftTab"]
        if "ТекущийТекст" not in (result["activeBeforePaste"] or ""):
            raise RuntimeError(
                "Не удалось сфокусировать поле ТекущийТекст: "
                + str(result)
                + " dump="
                + describe_agent_inputs(test)
            )
        replace_focused_text(test, prompt)
        result["promptValue"] = prompt_field_value(test)
        result["promptVisibleBeforeSend"] = marker in (result["promptValue"] or "")
        result["activeAfterPaste"] = focused_element_info(test)
        if not result["promptVisibleBeforeSend"]:
            raise RuntimeError(
                "Промпт не попал в поле ТекущийТекст после вставки из буфера: "
                + repr((result["promptValue"] or "")[:120])
                + " active="
                + str(result["activeAfterPaste"])
                + " dump="
                + describe_agent_inputs(test)
            )
        send_click = click_id_suffix(test, "_Отправить")
        if send_click == "missing":
            send_click = click_text_cdp(test, "Отправить")
        result["sendClick"] = send_click
        time.sleep(3)
        after = test._safe_body_text()
        if prompt_started(before, after, prompt):
            result["started"] = True
            result["attempts"] = attempt + 1
            return result
        press_enter(test)
        time.sleep(1.5)
        after = test._safe_body_text()
        if prompt_started(before, after, prompt):
            result["started"] = True
            result["attempts"] = attempt + 1
            result["startedViaEnter"] = True
            return result
        result["attempts"] = attempt + 1
        result["afterSendSample"] = after[:400]
    result["started"] = False
    result["dump"] = describe_agent_inputs(test)
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
        skip_query1c_prepare=True,
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
