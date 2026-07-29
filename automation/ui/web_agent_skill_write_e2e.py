# -*- coding: utf-8 -*-
"""Full E2E: ordinary AI Agent run selects a skill, writes a document, and shows its link."""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_skill_e2e import bsl_string, close_font_dialog
from automation.ui.web_query1c_test import BrowserQuery1CTest, Logger, WebUiConfig, setup_console_encoding


DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
DEFAULT_BRIDGE_URL = DEFAULT_WEB_URL + "/hs/codex-test/command"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'


def bridge_execute(bridge_url: str, code: str, timeout_sec: int = 180) -> dict:
    body = json.dumps({"command": "ExecuteBSL", "code": code, "params": []}, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        bridge_url,
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            payload = json.loads(response.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as error:
        details = error.read().decode("utf-8-sig", errors="replace")
        raise RuntimeError(f"Bridge HTTP {error.code}: {details}") from error
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload.get("result")


def make_skill_json(skill_name: str, skill_marker: str, document_marker: str) -> str:
    return json.dumps(
        {
            "name": skill_name,
            "title": "E2E запись заказа покупателя",
            "description": "Fixture skill for full write E2E of the ordinary AI Agent.",
            "enabled": True,
            "owner": "user",
            "scope": "user",
            "triggers": [skill_marker, "e2e write order", "заказ покупателя"],
            "dialog_types": ["Агент"],
            "target_object_type": "Document",
            "target_object_name": "ЗаказПокупателя",
            "prompt": (
                skill_marker
                + ": создай и запиши документ ЗаказПокупателя. Для e2e обязательно заполни "
                "Комментарий уникальным маркером " + document_marker + "."
            ),
            "risk_level": "write",
            "enforcement": "allow",
            "approval_required": False,
            "workflow": [],
            "template_vars": {
                "comment": {"type": "string", "required": True, "source": "user_prompt"},
                "target_object": {"type": "Document.ЗаказПокупателя", "required": True, "source": "skill"},
            },
            "dsl_template_mode": "strict",
            "dsl_template": {
                "dsl_version": 2,
                "steps": [
                    {
                        "action": "CreateDocument",
                        "object_name": "ЗаказПокупателя",
                        "data": {"Комментарий": "$comment"},
                        "operation_id": "create-order",
                    },
                    {"action": "Write", "operation_id": "write-order"},
                ],
            },
            "policy": {
                "risk_level": "write",
                "enforcement": "allow",
                "approval_required": False,
                "allowed_actions": ["CreateDocument", "SetField", "Write", "ShowInfo"],
                "forbidden_actions": ["DeleteObject"],
                "required_checks": [],
            },
        },
        ensure_ascii=False,
    )


def make_mock_queue(prompt: str, document_marker: str) -> str:
    plan = {
        "plan_version": 1,
        "goal": prompt,
        "last_user_text": prompt,
        "steps": [
            {
                "id": "step_create_order",
                "seq_no": 1,
                "kind": "create_document",
                "title": "Создать и записать заказ покупателя",
                "status": "pending",
                "input": {
                    "object_name": "ЗаказПокупателя",
                    "fields": {"Комментарий": document_marker},
                    "write": True,
                },
            }
        ],
    }
    summary = {
        "ТипОтвета": "Текст",
        "Текст": "Документ Заказ покупателя создан и записан. Маркер: " + document_marker,
        "RawModelText": "Документ Заказ покупателя создан и записан. Маркер: " + document_marker,
    }
    return json.dumps([json.dumps(plan, ensure_ascii=False), summary], ensure_ascii=False)


def prepare_and_run_agent(bridge_url: str, skill_name: str, skill_marker: str, prompt: str, document_marker: str) -> dict:
    skill_json = make_skill_json(skill_name, skill_marker, document_marker)
    mock_queue_json = make_mock_queue(prompt, document_marker)
    code = (
        "ИИА_Skills.УдалитьПользовательскийСкил(" + bsl_string(skill_name) + ");"
        "Карточка = ИИА_Skills.КарточкаИзJSON(" + bsl_string(skill_json) + ");"
        "ИИА_Skills.СохранитьПользовательскийСкил(Карточка);"
        "СсылкаДиалога = ИИА_Сервер.СоздатьНовыйДиалог(\"Администратор\", Перечисления.ИИА_ТипДиалога.Агент);"
        "ЧтениеJSON = Новый ЧтениеJSON; ЧтениеJSON.УстановитьСтроку(" + bsl_string(mock_queue_json) + ");"
        "Очередь = ПрочитатьJSON(ЧтениеJSON); ЧтениеJSON.Закрыть();"
        "ИИА_AIInvocation.УстановитьОчередьMockОтветов(СсылкаДиалога, Очередь);"
        "ИИА_Оркестратор.ОтправитьИЗапустить(СсылкаДиалога, " + bsl_string(prompt) + ", Перечисления.ИИА_ТипДиалога.Агент);"
        "РезультатВыполнения = Новый Структура(\"dialog,prompt\", Строка(СсылкаДиалога), " + bsl_string(prompt) + ");"
    )
    return bridge_execute(bridge_url, code)


def continue_without_confirmation(bridge_url: str, document_marker: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура(\"dialog,continued\", \"\", Ложь);"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 20 Диалоги.Ссылка КАК Ссылка ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.ТипДиалога = &ТипДиалога УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.Агент);"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Пока Выборка.Следующий() Цикл "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект(); Найден = Ложь;"
        "Для Каждого Сообщение Из Диалог.Сообщения Цикл "
        "Если СтрНайти(Строка(Сообщение.Текст), " + bsl_string(document_marker) + ") > 0 Тогда Найден = Истина; Прервать; КонецЕсли; "
        "КонецЦикла;"
        "Если Найден Тогда "
        "РезультатВыполнения.dialog = Строка(Выборка.Ссылка);"
        "РезультатВыполнения.continued = ИИА_ВызовСервера.ОркестраторВыполнятьБезПодтверждения(Выборка.Ссылка);"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code, timeout_sec=180)


def get_dialog_approval_state(bridge_url: str, document_marker: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура(\"dialog,pending,status\", \"\", Ложь, \"\");"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 20 Диалоги.Ссылка КАК Ссылка ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.ТипДиалога = &ТипДиалога УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.Агент);"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Пока Выборка.Следующий() Цикл "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект(); Найден = Ложь;"
        "Для Каждого Сообщение Из Диалог.Сообщения Цикл "
        "Если СтрНайти(Строка(Сообщение.Текст), " + bsl_string(document_marker) + ") > 0 Тогда Найден = Истина; Прервать; КонецЕсли; "
        "КонецЦикла;"
        "Если Найден Тогда "
        "Состояние = ИИА_Сервер.ПолучитьСостояниеПодтверждения(Выборка.Ссылка);"
        "РезультатВыполнения.dialog = Строка(Выборка.Ссылка);"
        "Если Состояние <> Неопределено И Состояние.Свойство(\"status\") Тогда "
        "РезультатВыполнения.status = Строка(Состояние.status);"
        "РезультатВыполнения.pending = ВРег(Строка(Состояние.status)) = \"PENDING\";"
        "КонецЕсли;"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code)


def wait_for_approval(bridge_url: str, document_marker: str, timeout_sec: int) -> dict:
    deadline = time.time() + timeout_sec
    last_state: dict = {}
    while time.time() < deadline:
        last_state = get_dialog_approval_state(bridge_url, document_marker)
        if last_state.get("pending"):
            return last_state
        time.sleep(1)
    return last_state


def set_write_access(bridge_url: str, user: str, enabled: bool) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура;"
        "НаборЗаписей = РегистрыСведений.ИИА_НастройкиПользователей.СоздатьНаборЗаписей();"
        "НаборЗаписей.Отбор.Пользователь.Установить(" + bsl_string(user) + ");"
        "НаборЗаписей.Прочитать();"
        "РезультатВыполнения.Вставить(\"hadRecord\", НаборЗаписей.Количество() > 0);"
        "Если НаборЗаписей.Количество() = 0 Тогда "
        "Запись = НаборЗаписей.Добавить(); Запись.Пользователь = " + bsl_string(user) + ";"
        "Запись.Модель = \"gpt-5.4-nano\"; Запись.ЛимитТокеновНаЗапуск = 50000;"
        "Иначе Запись = НаборЗаписей[0]; КонецЕсли;"
        "РезультатВыполнения.Вставить(\"oldWriteAccess\", Запись.ДоступнаЗапись);"
        "Запись.ДоступнаЗапись = " + ("Истина" if enabled else "Ложь") + ";"
        "НаборЗаписей.Записать();"
        "РезультатВыполнения.Вставить(\"newWriteAccess\", Запись.ДоступнаЗапись);"
    )
    return bridge_execute(bridge_url, code)


def restore_write_access(bridge_url: str, user: str, snapshot: dict | None) -> None:
    if not snapshot:
        return
    old_value = bool(snapshot.get("oldWriteAccess", True))
    had_record = bool(snapshot.get("hadRecord", True))
    if had_record:
        set_write_access(bridge_url, user, old_value)
        return
    code = (
        "РезультатВыполнения = Новый Структура;"
        "НаборЗаписей = РегистрыСведений.ИИА_НастройкиПользователей.СоздатьНаборЗаписей();"
        "НаборЗаписей.Отбор.Пользователь.Установить(" + bsl_string(user) + ");"
        "НаборЗаписей.Прочитать();"
        "НаборЗаписей.Очистить();"
        "НаборЗаписей.Записать();"
        "РезультатВыполнения.Вставить(\"removedCreatedRecord\", Истина);"
    )
    bridge_execute(bridge_url, code)


def inspect_result(bridge_url: str, skill_name: str, skill_marker: str, document_marker: str) -> dict:
    code = (
        "РезультатВыполнения = Новый Структура;"
        "РезультатВыполнения.Вставить(\"docFound\", Ложь);"
        "РезультатВыполнения.Вставить(\"changedObjectsCount\", 0);"
        "РезультатВыполнения.Вставить(\"dialogHasChangedObject\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasSkillName\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasSkillMarker\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasWrite\", Ложь);"
        "РезультатВыполнения.Вставить(\"logHasObjectWritten\", Ложь);"
        "ЗапросДок = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 50 Док.Ссылка КАК Ссылка, Док.Комментарий КАК Комментарий "
        "ИЗ Документ.ЗаказПокупателя КАК Док УПОРЯДОЧИТЬ ПО Док.Дата УБЫВ\");"
        "ВыборкаДок = ЗапросДок.Выполнить().Выбрать();"
        "Пока ВыборкаДок.Следующий() Цикл "
        "Если Строка(ВыборкаДок.Комментарий) <> " + bsl_string(document_marker) + " Тогда Продолжить; КонецЕсли;"
        "РезультатВыполнения.docFound = Истина;"
        "РезультатВыполнения.Вставить(\"docPresentation\", Строка(ВыборкаДок.Ссылка));"
        "РезультатВыполнения.Вставить(\"docGuid\", Строка(ВыборкаДок.Ссылка.УникальныйИдентификатор()));"
        "Прервать; КонецЦикла;"
        "Запрос = Новый Запрос(\"ВЫБРАТЬ ПЕРВЫЕ 20 Диалоги.Ссылка КАК Ссылка ИЗ Справочник.ИИА_Диалоги КАК Диалоги "
        "ГДЕ Диалоги.ТипДиалога = &ТипДиалога УПОРЯДОЧИТЬ ПО Диалоги.ДатаСоздания УБЫВ\");"
        "Запрос.УстановитьПараметр(\"ТипДиалога\", Перечисления.ИИА_ТипДиалога.Агент);"
        "Выборка = Запрос.Выполнить().Выбрать();"
        "Пока Выборка.Следующий() Цикл "
        "Диалог = Выборка.Ссылка.ПолучитьОбъект(); Найден = Ложь;"
        "Для Каждого Сообщение Из Диалог.Сообщения Цикл "
        "Если СтрНайти(Строка(Сообщение.Текст), " + bsl_string(document_marker) + ") > 0 Тогда Найден = Истина; Прервать; КонецЕсли; КонецЦикла;"
        "Если Найден Тогда "
        "Лог = ИИА_Сервер.ПолучитьЛогДиалога(Выборка.Ссылка);"
        "РезультатВыполнения.Вставить(\"dialog\", Строка(Выборка.Ссылка));"
        "РезультатВыполнения.logHasSkillName = СтрНайти(Лог, " + bsl_string(skill_name) + ") > 0;"
        "РезультатВыполнения.logHasSkillMarker = СтрНайти(Лог, " + bsl_string(skill_marker) + ") > 0;"
        "РезультатВыполнения.logHasWrite = СтрНайти(Лог, \"Write\") > 0;"
        "РезультатВыполнения.logHasObjectWritten = СтрНайти(Лог, \"object_written\") > 0 ИЛИ СтрНайти(Лог, \"Объект успешно записан\") > 0;"
        "РезультатВыполнения.changedObjectsCount = Диалог.ИзмененныеОбъекты.Количество();"
        "Для Каждого СтрокаИзмененных Из Диалог.ИзмененныеОбъекты Цикл "
        "Если РезультатВыполнения.Свойство(\"docGuid\") И Строка(СтрокаИзмененных.СсылкаНаОбъект.УникальныйИдентификатор()) = РезультатВыполнения.docGuid Тогда "
        "РезультатВыполнения.dialogHasChangedObject = Истина; КонецЕсли; КонецЦикла;"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code)


def wait_for_result(bridge_url: str, skill_name: str, skill_marker: str, document_marker: str, timeout_sec: int) -> dict:
    deadline = time.time() + timeout_sec
    last_result: dict = {}
    while time.time() < deadline:
        try:
            last_result = inspect_result(bridge_url, skill_name, skill_marker, document_marker)
        except RuntimeError as error:
            last_result = {"inspectError": str(error)}
        if last_result.get("docFound") and last_result.get("dialogHasChangedObject"):
            return last_result
        time.sleep(1)
    return last_result


def open_agent_and_check_link(args: argparse.Namespace, document_marker: str, doc_presentation: str) -> dict:
    artifact_dir = Path(args.artifact_dir)
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
        log_file=str(artifact_dir / "web_agent_skill_write_e2e.log"),
        artifact_dir=str(artifact_dir),
        headless=not args.headed,
        skip_com_prepare=True,
    )
    test = BrowserQuery1CTest(config, Logger(config.log_file))
    try:
        test._launch_browser()
        test._open_initial_target()
        font_closed = close_font_dialog()
        command = urllib.parse.quote("CommonCommand.ИИА_Агент", safe=".")
        test._session_call("Page.navigate", {"url": args.web_url.rstrip("/") + "/#e1cib/command/" + command})
        test._wait_until_text_contains("ИИ Агент", args.timeout_sec)
        test._wait_until_text_contains("Заказ покупателя", args.timeout_sec)
        body = test._safe_body_text()
        (artifact_dir / "web_agent_skill_write_e2e_body.txt").write_text(body, encoding="utf-8")
        return {
            "fontDialogClosed": font_closed,
            "uiHasOrderPresentation": "Заказ покупателя" in body,
            "uiHasDocumentMarker": document_marker in body,
            "uiHasDocPresentation": bool(doc_presentation) and doc_presentation in body,
            "bodyHead": body[:1500],
        }
    finally:
        test._close()


def cleanup_skill(bridge_url: str, skill_name: str) -> None:
    try:
        bridge_execute(bridge_url, "Попытка ИИА_Skills.УдалитьПользовательскийСкил(" + bsl_string(skill_name) + "); Исключение КонецПопытки; РезультатВыполнения = Истина;")
    except Exception:
        pass


def run(args: argparse.Namespace) -> dict:
    artifact_dir = Path(args.artifact_dir)
    artifact_dir.mkdir(parents=True, exist_ok=True)
    suffix = time.strftime("%Y%m%d%H%M%S")
    skill_name = args.skill_name
    skill_marker = "E2E_WRITE_SKILL_" + suffix
    document_marker = "E2E_ORDER_CREATED_BY_AGENT_" + suffix
    prompt = skill_marker + ": создай и запиши тестовый заказ покупателя. Комментарий: " + document_marker
    result: dict[str, object] = {
        "skillName": skill_name,
        "skillMarker": skill_marker,
        "documentMarker": document_marker,
    }
    write_access_snapshot: dict | None = None
    try:
        write_access_snapshot = set_write_access(args.bridge_url, args.user, True)
        result["writeAccess"] = write_access_snapshot
        result["run"] = prepare_and_run_agent(args.bridge_url, skill_name, skill_marker, prompt, document_marker)
        result["approvalStateBeforeContinue"] = wait_for_approval(args.bridge_url, document_marker, args.timeout_sec)
        if result["approvalStateBeforeContinue"].get("pending"):
            result["approvalContinue"] = continue_without_confirmation(args.bridge_url, document_marker)
        else:
            result["approvalContinue"] = {"continued": False, "reason": "approval_not_pending"}
        result["approvalContinued"] = bool(result["approvalContinue"].get("continued"))
        inspected = wait_for_result(args.bridge_url, skill_name, skill_marker, document_marker, args.timeout_sec)
        result.update(inspected)
        ui = open_agent_and_check_link(args, document_marker, str(inspected.get("docPresentation", "")))
        result.update(ui)
        required = [
            "docFound",
            "dialogHasChangedObject",
            "approvalContinued",
            "logHasSkillMarker",
            "logHasObjectWritten",
            "uiHasOrderPresentation",
            "uiHasDocPresentation",
        ]
        result["success"] = all(bool(result.get(key)) for key in required)
        result["required"] = {key: bool(result.get(key)) for key in required}
        return result
    finally:
        cleanup_skill(args.bridge_url, skill_name)
        restore_write_access(args.bridge_url, args.user, write_access_snapshot)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Full write E2E for ordinary AI Agent skill run")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--chrome-exe", default=r"C:\Program Files\Google\Chrome\Application\chrome.exe")
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--skill-name", default="user-skill-agent-write-e2e")
    parser.add_argument("--timeout-sec", type=int, default=60)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "web_skills_artifacts"))
    parser.add_argument("--headed", action="store_true", help="Show Chrome window for manual debugging. Headless is default.")
    return parser.parse_args()


def main() -> int:
    setup_console_encoding()
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_agent_skill_write_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
