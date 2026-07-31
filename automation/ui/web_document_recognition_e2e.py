# -*- coding: utf-8 -*-
"""E2E UI check for the document recognition agent mode."""

from __future__ import annotations

import argparse
import base64
import io
import json
import mimetypes
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


def switch_mode(test: BrowserQuery1CTest, mode: str) -> dict:
    before = focus_mode_field(test)
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


def inspect_dialog(bridge_url: str, marker: str, expected_skill: str, expected_target: str, expected_file_name: str) -> dict:
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
        "РезультатВыполнения.logHasPrompt = СтрНайти(Лог, " + bsl_string(marker) + ") > 0;"
        "РезультатВыполнения.logHasRecognitionPrompt = СтрНайти(Лог, \"РЕЖИМ: РАСПОЗНАВАНИЕ ДОКУМЕНТОВ\") > 0;"
        "РезультатВыполнения.logHasSkill = СтрНайти(Лог, " + bsl_string(expected_skill) + ") > 0;"
        "РезультатВыполнения.logHasAttachment = СтрНайти(Лог, " + bsl_string(expected_file_name) + ") > 0;"
        "РезультатВыполнения.logHasTarget = СтрНайти(Лог, " + bsl_string("target_object_name=" + expected_target) + ") > 0;"
        "РезультатВыполнения.logHasDslTemplate = СтрНайти(Лог, \"DSL_TEMPLATE_JSON\") > 0;"
        "Позиция = СтрНайти(Лог, " + bsl_string(expected_skill) + ");"
        "Если Позиция > 0 Тогда РезультатВыполнения.Вставить(\"aroundSkill\", Сред(Лог, Макс(1, Позиция - 120), 420)); КонецЕсли;"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code)


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
    try:
        test._launch_browser()
        test._open_initial_target()
        result["fontDialogClosed"] = close_font_dialog()
        command = urllib.parse.quote("CommonCommand.ИИА_Агент", safe=".")
        test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
        test._wait_until_text_contains("ИИ Агент", args.timeout_sec)
        result["modeSwitch"] = switch_mode(test, "РаспознаваниеДокументов")
        result["newDialogClick"] = click_label(test, "Новый диалог")
        time.sleep(2)
        attachment_base64, expected_file_name, _extension = read_attachment_base64(args.image_path)
        result["attachmentBytes"] = len(base64.b64decode(attachment_base64))
        result["attachmentMime"] = mimetypes.guess_type(expected_file_name)[0] or ""
        result["attachment"] = attach_image_to_latest_recognition_dialog(args.bridge_url, args.image_path)
        test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
        test._wait_until_text_contains("ИИ Агент", args.timeout_sec)
        time.sleep(2)
        result["promptFocus"] = focus_prompt(test)
        prompt = marker + ": " + args.prompt
        replace_focused_text(test, prompt)
        result["sendClick"] = click_label(test, "Отправить")
        time.sleep(args.agent_wait_sec)
        body_text = test._safe_body_text()
        result["promptVisible"] = marker in body_text
        result["bodyHead"] = body_text[:1200]
        (artifact_dir / "web_document_recognition_e2e_body.txt").write_text(body_text, encoding="utf-8")
        result.update(inspect_dialog(args.bridge_url, marker, args.expected_skill, args.expected_target, expected_file_name))
        required = ["modeSwitch", "attachment", "found", "logHasPrompt", "logHasRecognitionPrompt", "logHasSkill", "logHasAttachment", "logHasTarget", "logHasDslTemplate"]
        checks = {
            "modeSwitch": bool(result.get("modeSwitch", {}).get("ok")),
            "attachment": bool(result.get("attachment", {}).get("attached")),
            "found": bool(result.get("found")),
            "logHasPrompt": bool(result.get("logHasPrompt")),
            "logHasRecognitionPrompt": bool(result.get("logHasRecognitionPrompt")),
            "logHasSkill": bool(result.get("logHasSkill")),
            "logHasAttachment": bool(result.get("logHasAttachment")),
            "logHasTarget": bool(result.get("logHasTarget")),
            "logHasDslTemplate": bool(result.get("logHasDslTemplate")),
        }
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
