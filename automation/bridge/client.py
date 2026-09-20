# -*- coding: utf-8 -*-
"""HTTP-клиент Codex Test Bridge для вызова 1С без COM."""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from typing import Any


def bsl_string(value: Any) -> str:
    return '"' + str(value).replace('"', '""') + '"'


def bsl_bool(value: bool) -> str:
    return "Истина" if value else "Ложь"


def dialog_enum_name(dialog_type: str) -> str:
    mapping = {"Agent": "Агент", "Агент": "Агент", "Запрос1С": "Запрос1С", "Zapros1S": "Запрос1С"}
    return mapping.get(dialog_type, "Запрос1С")


def request_json(url: str, payload: dict | None = None, timeout: int = 60) -> dict:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    if payload is None:
        req = urllib.request.Request(url, method="GET")
    else:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
    try:
        with opener.open(req, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8-sig"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8-sig", errors="replace")
        raise RuntimeError(f"Bridge HTTP {exc.code}: {details}") from exc


def execute_bsl(bridge_url: str, code: str, timeout: int = 60) -> Any:
    payload = request_json(
        bridge_url.rstrip("/") + "/command",
        {"command": "ExecuteBSL", "code": code, "params": []},
        timeout=timeout,
    )
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload.get("result")


def call_exported(bridge_url: str, module: str, method: str, *args: str, timeout: int = 60) -> Any:
    joined = ", ".join(args)
    return execute_bsl(
        bridge_url,
        f"РезультатВыполнения = {module}.{method}({joined});",
        timeout=timeout,
    )


def query(bridge_url: str, text: str, limit: int = 10, timeout: int = 60) -> dict:
    payload = request_json(
        bridge_url.rstrip("/") + "/command",
        {"command": "Query", "text": text, "limit": limit, "params": {}},
        timeout=timeout,
    )
    if not payload.get("ok"):
        raise RuntimeError(payload)
    return payload


def start_agent_dialog(
    bridge_url: str,
    user: str,
    text: str,
    dialog_type: str,
    auto_confirm: bool,
    timeout: int = 60,
) -> str:
    enum_name = dialog_enum_name(dialog_type)
    code = f"""
Пользователь = {bsl_string(user)};
ТекстЗадачи = {bsl_string(text)};
ТипДиалога = Перечисления.ИИА_ТипДиалога.{enum_name};
СсылкаДиалога = ИИА_Сервер.СоздатьНовыйДиалог(Пользователь, ТипДиалога);
ИИА_Сервер.ОтправитьСообщениеСервера(СсылкаДиалога, ТипДиалога, ТекстЗадачи);
Если {bsl_bool(auto_confirm)} Тогда
    ИИА_Сервер.УстановитьРежимБезПодтверждения(СсылкаДиалога, Истина);
КонецЕсли;
НаборЗаписей = РегистрыСведений.ИИА_НастройкиПользователей.СоздатьНаборЗаписей();
НаборЗаписей.Отбор.Пользователь.Установить(Пользователь);
НаборЗаписей.Прочитать();
Если НаборЗаписей.Количество() = 0 Тогда
    Запись = НаборЗаписей.Добавить();
    Запись.Пользователь = Пользователь;
Иначе
    Запись = НаборЗаписей[0];
КонецЕсли;
Если Запись.ЛимитТокеновНаЗапуск <= 0 Или Запись.ЛимитТокеновНаЗапуск < 50000 Тогда
    Запись.ЛимитТокеновНаЗапуск = 50000;
    НаборЗаписей.Записать();
КонецЕсли;
ИИА_Оркестратор.Запустить(СсылкаДиалога);
РезультатВыполнения = Строка(СсылкаДиалога.УникальныйИдентификатор());
"""
    uuid = str(execute_bsl(bridge_url, code, timeout=timeout) or "").strip()
    if not uuid:
        raise RuntimeError("Bridge не вернул UUID диалога")
    return uuid


def poll_agent_dialog(bridge_url: str, uuid: str, timeout: int = 60) -> dict:
    code = f"""
СсылкаДиалога = Справочники.ИИА_Диалоги.ПолучитьСсылку(Новый УникальныйИдентификатор({bsl_string(uuid)}));
Проверка = ИИА_Сервер.ПолучитьРезультатПроверкиИзХранилища(СсылкаДиалога);
СтатусПроверки = "";
Если Проверка <> Неопределено И ТипЗнч(Проверка) = Тип("Структура") И Проверка.Свойство("СтатусПроверкиЗадачи") Тогда
    СтатусПроверки = Строка(Проверка.СтатусПроверкиЗадачи);
КонецЕсли;
РезультатВыполнения = Новый Структура;
РезультатВыполнения.Вставить("running", ИИА_Сервер.ОркестраторВключенДляДиалога(СсылкаДиалога));
РезультатВыполнения.Вставить("status", СтатусПроверки);
РезультатВыполнения.Вставить("tokens", ИИА_Сервер.ПолучитьОбщееКоличествоТокенов(СсылкаДиалога));
"""
    result = execute_bsl(bridge_url, code, timeout=timeout)
    if not isinstance(result, dict):
        raise RuntimeError(f"Неожиданный ответ poll: {result!r}")
    return result


def fetch_agent_dialog(bridge_url: str, uuid: str, timeout: int = 90) -> dict:
    code = f"""
СсылкаДиалога = Справочники.ИИА_Диалоги.ПолучитьСсылку(Новый УникальныйИдентификатор({bsl_string(uuid)}));
Проверка = ИИА_Сервер.ПолучитьРезультатПроверкиИзХранилища(СсылкаДиалога);
СтатусПроверки = "";
Если Проверка <> Неопределено И ТипЗнч(Проверка) = Тип("Структура") И Проверка.Свойство("СтатусПроверкиЗадачи") Тогда
    СтатусПроверки = Строка(Проверка.СтатусПроверкиЗадачи);
КонецЕсли;
РезультатВыполнения = Новый Структура;
РезультатВыполнения.Вставить("Успех", СтатусПроверки = "Успешно");
РезультатВыполнения.Вставить("Лог", ИИА_Сервер.ПолучитьЛогДиалога(СсылкаДиалога));
РезультатВыполнения.Вставить("UsageTokens", ИИА_Сервер.ПолучитьОбщееКоличествоТокенов(СсылкаДиалога));
РезультатВыполнения.Вставить("СтатусПроверкиЗадачи", СтатусПроверки);
РезультатВыполнения.Вставить("СсылкаДиалога", {bsl_string(uuid)});
РезультатВыполнения.Вставить("running", ИИА_Сервер.ОркестраторВключенДляДиалога(СсылкаДиалога));
"""
    result = execute_bsl(bridge_url, code, timeout=timeout)
    if not isinstance(result, dict):
        raise RuntimeError(f"Неожиданный ответ fetch: {result!r}")
    return result


def run_agent_dialog(
    bridge_url: str,
    user: str,
    text: str,
    dialog_type: str,
    auto_confirm: bool = False,
    wait_timeout_sec: int = 900,
    poll_sec: int = 5,
) -> dict:
    uuid = start_agent_dialog(bridge_url, user, text, dialog_type, auto_confirm)
    deadline = time.time() + wait_timeout_sec
    last: dict = {}
    while time.time() < deadline:
        last = poll_agent_dialog(bridge_url, uuid)
        if not last.get("running"):
            result = fetch_agent_dialog(bridge_url, uuid)
            result["dialog_uuid"] = uuid
            return result
        time.sleep(poll_sec)
    result = fetch_agent_dialog(bridge_url, uuid)
    result["dialog_uuid"] = uuid
    result["timeout"] = True
    result["poll_last"] = last
    return result


def prepare_query1c_dialog(
    bridge_url: str,
    user: str,
    query_text: str,
    query_params_json: str = "",
    timeout: int = 60,
) -> str:
    code = f"""
Пользователь = {bsl_string(user)};
ТипДиалога = Перечисления.ИИА_ТипДиалога.Запрос1С;
СсылкаДиалога = ИИА_Сервер.СоздатьНовыйДиалог(Пользователь, ТипДиалога);
ИИА_Сервер.СохранитьЧерновикЗапроса1С(СсылкаДиалога, {bsl_string(query_text)}, {bsl_string(query_params_json)});
РезультатВыполнения = Строка(СсылкаДиалога.УникальныйИдентификатор());
"""
    uuid = str(execute_bsl(bridge_url, code, timeout=timeout) or "").strip()
    if not uuid:
        raise RuntimeError("Bridge не вернул UUID диалога Запрос1С")
    return uuid
