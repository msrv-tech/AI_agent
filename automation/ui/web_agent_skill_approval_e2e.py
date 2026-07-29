# -*- coding: utf-8 -*-
"""E2E approval branches for ordinary AI Agent skill write runs."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from automation.ui.web_agent_skill_e2e import bsl_string
from automation.ui.web_agent_skill_write_e2e import (
    DEFAULT_BRIDGE_URL,
    bridge_execute,
    cleanup_skill,
    continue_without_confirmation,
    inspect_result,
    prepare_and_run_agent,
    restore_write_access,
    set_write_access,
    wait_for_approval,
    wait_for_result,
)


def continue_with_action(bridge_url: str, document_marker: str, action: str) -> dict:
    method = {
        "approve": "ОркестраторПодтвердитьОжидающееДействие",
        "reject": "ОркестраторОтклонитьОжидающееДействие",
    }[action]
    code = (
        "РезультатВыполнения = Новый Структура(\"dialog,continued,action\", \"\", Ложь, " + bsl_string(action) + ");"
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
        "РезультатВыполнения.continued = ИИА_ВызовСервера." + method + "(Выборка.Ссылка);"
        "Прервать; КонецЕсли; КонецЦикла;"
    )
    return bridge_execute(bridge_url, code, timeout_sec=180)


def run_scenario(args: argparse.Namespace, action: str, index: int) -> dict:
    suffix = time.strftime("%Y%m%d%H%M%S") + "_" + str(index)
    skill_name = args.skill_name + "-" + action
    skill_marker = "E2E_APPROVAL_SKILL_" + action.upper() + "_" + suffix
    document_marker = "E2E_APPROVAL_ORDER_" + action.upper() + "_" + suffix
    prompt = skill_marker + ": создай и запиши тестовый заказ покупателя. Комментарий: " + document_marker
    result: dict[str, object] = {
        "action": action,
        "skillName": skill_name,
        "skillMarker": skill_marker,
        "documentMarker": document_marker,
    }

    result["run"] = prepare_and_run_agent(args.bridge_url, skill_name, skill_marker, prompt, document_marker)
    result["approvalState"] = wait_for_approval(args.bridge_url, document_marker, args.timeout_sec)
    if not result["approvalState"].get("pending"):
        result["success"] = False
        result["required"] = {"approvalPending": False}
        return result

    if action == "without_confirmation":
        result["continue"] = continue_without_confirmation(args.bridge_url, document_marker)
    else:
        result["continue"] = continue_with_action(args.bridge_url, document_marker, action)
    result["continued"] = bool(result["continue"].get("continued"))

    if action == "reject":
        time.sleep(3)
        inspected = inspect_result(args.bridge_url, skill_name, skill_marker, document_marker)
        result.update(inspected)
        required = {
            "approvalPending": True,
            "continued": result["continued"],
            "docNotFound": not bool(result.get("docFound")),
            "noChangedObjects": int(result.get("changedObjectsCount", 0)) == 0,
            "logHasSkillMarker": bool(result.get("logHasSkillMarker")),
        }
    else:
        inspected = wait_for_result(args.bridge_url, skill_name, skill_marker, document_marker, args.timeout_sec)
        result.update(inspected)
        required = {
            "approvalPending": True,
            "continued": result["continued"],
            "docFound": bool(result.get("docFound")),
            "dialogHasChangedObject": bool(result.get("dialogHasChangedObject")),
            "logHasObjectWritten": bool(result.get("logHasObjectWritten")),
        }

    result["required"] = required
    result["success"] = all(required.values())
    return result


def run(args: argparse.Namespace) -> dict:
    Path(args.artifact_dir).mkdir(parents=True, exist_ok=True)
    write_access_snapshot: dict | None = None
    result: dict[str, object] = {"scenarios": []}
    try:
        write_access_snapshot = set_write_access(args.bridge_url, args.user, True)
        result["writeAccess"] = write_access_snapshot
        for index, action in enumerate(("reject", "approve", "without_confirmation"), start=1):
            scenario = run_scenario(args, action, index)
            result["scenarios"].append(scenario)
            cleanup_skill(args.bridge_url, str(scenario.get("skillName", "")))
        result["success"] = all(item.get("success") for item in result["scenarios"])
        return result
    finally:
        for action in ("reject", "approve", "without_confirmation"):
            cleanup_skill(args.bridge_url, args.skill_name + "-" + action)
        restore_write_access(args.bridge_url, args.user, write_access_snapshot)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Approval branch E2E for AI Agent skill writes")
    parser.add_argument("--bridge-url", default=DEFAULT_BRIDGE_URL)
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--skill-name", default="user-skill-agent-approval-e2e")
    parser.add_argument("--timeout-sec", type=int, default=90)
    parser.add_argument("--artifact-dir", default=str(REPO_ROOT / "automation" / "logs" / "web_skills_artifacts"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = run(args)
    out = Path(args.artifact_dir) / "web_agent_skill_approval_e2e_result.json"
    out.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
