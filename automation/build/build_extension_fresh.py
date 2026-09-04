# -*- coding: utf-8 -*-
"""Prepare and optionally build the 1C:Fresh edition of the extension.

The repository XML remains the single source of truth. Fresh-only changes are
applied to a temporary copy, which is then loaded into a compatible test base
and dumped as CFE.

Examples:
    python automation/build/build_extension_fresh.py --prepare-only
    python automation/build/build_extension_fresh.py --build \
        --connection-string 'Srvr="server";Ref="base";' --user Admin

Passwords should be passed through FRESH_1C_PASSWORD, not command history.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = PROJECT_ROOT / "xml"
DEFAULT_PREPARED = PROJECT_ROOT / "temp" / "fresh_build" / "xml"
DEFAULT_OUTPUT = PROJECT_ROOT / "bin" / "AI_Agent_Fresh.cfe"
EXTENSION_NAME = "ИИ_Агент"

GITHUB_MODULE = Path("CommonModules") / "ИИА_GitsellСервер" / "Ext" / "Module.bsl"
SETTINGS_MODULE = Path("CommonForms") / "ИИА_Настройки" / "Ext" / "Form" / "Module.bsl"
SETTINGS_FORM = Path("CommonForms") / "ИИА_Настройки" / "Ext" / "Form.xml"
DIALOG_LOG_MODULE = Path("CommonModules") / "ИИА_DialogLog" / "Ext" / "Module.bsl"
PROVIDERS_MODULE = Path("CommonModules") / "ИИА_Провайдеры" / "Ext" / "Module.bsl"
GITSELL_MODULE = Path("CommonModules") / "ИИА_GitsellСервер" / "Ext" / "Module.bsl"

FRESH_PROVIDER_URLS = (
    "https://gitsell.ru/api/v1",
    "https://api.giga.chat/v1",
    "https://ai.api.cloud.yandex.net/v1",
)

UPDATE_FORM_NAMES = (
    "ЕстьОбновление",
    "НоваяВерсия",
    "СсылкаНаСкачивание",
    "ОбновитьРасширение",
    "СкачатьРасширение",
    "ГруппаОбновление",
)

FORBIDDEN_FRESH_MARKERS = {
    "РасширенияКонфигурации": "access to extension records",
    "api.github.com": "GitHub update API",
    "github_проверитьобновление": "self-update code",
    "github_скачатьфайл": "self-update download",
}

FRESH_ALLOWED_EXTERNAL_HOSTS = {
    "gitsell.ru",
    "api.giga.chat",
    "ngw.devices.sberbank.ru",
    "ai.api.cloud.yandex.net",
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8-sig", newline="")


def remove_bsl_routine(content: str, name: str) -> str:
    pattern = re.compile(
        rf"(?ms)^(?:&[^\r\n]+\r?\n)*"
        rf"(?:Процедура|Функция)\s+{re.escape(name)}\s*\([^\r\n]*\).*?"
        rf"^Конец(?:Процедуры|Функции)\s*;?\s*\r?\n?"
    )
    result, count = pattern.subn("", content)
    if count != 1:
        raise RuntimeError(f"Expected one BSL routine {name!r}, found {count}")
    return result


def remove_named_xml_element(content: str, name: str) -> str:
    start_re = re.compile(rf'<(?P<tag>[A-Za-z]+)\s+name="{re.escape(name)}"[^>]*>')
    match = start_re.search(content)
    if not match:
        raise RuntimeError(f"XML element with name={name!r} not found")
    opening = match.group(0)
    if opening.rstrip().endswith("/>"):
        return content[: match.start()] + content[match.end() :]
    tag = match.group("tag")
    token_re = re.compile(rf'<(?:/{tag}\s*|{tag}\b[^>]*)>')
    depth = 1
    for token in token_re.finditer(content, match.end()):
        value = token.group(0)
        if value.startswith(f"</{tag}"):
            depth -= 1
        elif not value.rstrip().endswith("/>"):
            depth += 1
        if depth == 0:
            line_start = content.rfind("\n", 0, match.start()) + 1
            end = token.end()
            if end < len(content) and content[end : end + 2] == "\r\n":
                end += 2
            elif end < len(content) and content[end] == "\n":
                end += 1
            return content[:line_start] + content[end:]
    raise RuntimeError(f"Closing tag for XML element name={name!r} not found")


def remove_self_update(xml_root: Path) -> None:
    server_path = xml_root / GITHUB_MODULE
    content = read_text(server_path)
    region = re.compile(
        r"(?ms)^#Область\s+GitHub_Updater\s*$.*?^#КонецОбласти\s*$\r?\n?"
    )
    content, count = region.subn("", content)
    if count != 1:
        raise RuntimeError(f"Expected one GitHub_Updater region, found {count}")
    write_text(server_path, content)

    form_module_path = xml_root / SETTINGS_MODULE
    content = read_text(form_module_path)
    update_probe = re.compile(
        r"(?ms)^\s*Попытка\s*\r?\n"
        r"\s*РезультатОбновления\s*=\s*"
        r"ИИА_GitsellСервер\.GitHub_ПроверитьОбновление\(\);.*?"
        r"^\s*КонецПопытки;\s*\r?\n?"
    )
    content, count = update_probe.subn("", content)
    if count != 1:
        raise RuntimeError(f"Expected one settings update probe, found {count}")
    for routine in ("ОбновитьРасширение", "СкачатьРасширение", "ОбновитьРасширениеНаСервере"):
        content = remove_bsl_routine(content, routine)
    write_text(form_module_path, content)

    form_path = xml_root / SETTINGS_FORM
    form_content = read_text(form_path)
    for name in UPDATE_FORM_NAMES:
        form_content = remove_named_xml_element(form_content, name)
    write_text(form_path, form_content)


def remove_server_debug_file_log(xml_root: Path) -> None:
    path = xml_root / DIALOG_LOG_MODULE
    content = read_text(path)
    block = re.compile(
        r"(?ms)^\s*Попытка\s*\r?\n"
        r"\s*ДиалогОбъект\s*=.*?"
        r"ПутьКЛогуОтладки.*?"
        r"^\s*КонецПопытки;\s*\r?\n?"
    )
    content, count = block.subn("", content)
    if count != 2:
        raise RuntimeError(f"Expected two server debug-file blocks, found {count}")
    write_text(path, content)


def adapt_fresh_provider_form(xml_root: Path) -> None:
    """Replace arbitrary URL editing with the three audited Fresh providers."""
    path = xml_root / SETTINGS_FORM
    content = read_text(path)
    content = content.replace(
        "<v8:content>Адрес сервера</v8:content>",
        "<v8:content>ИИ-провайдер</v8:content>",
    )
    marker = "\t\t\t\t\t<DataPath>Provider_BaseUrl</DataPath>"
    replacement = marker + "\r\n\t\t\t\t\t<ListChoiceMode>true</ListChoiceMode>"
    if content.count(marker) != 1:
        raise RuntimeError("Expected one Provider_BaseUrl field in settings form")
    content = content.replace(marker, replacement)
    write_text(path, content)

    path = xml_root / SETTINGS_MODULE
    content = read_text(path)
    old = """\tНастройки = ИИА_Сервер.ПолучитьНастройкиПользователя();
\tProvider_ApiKey = Настройки.Provider_ApiKey;
\tProvider_BaseUrl = Настройки.Provider_BaseUrl;"""
    new = """\tНастройки = ИИА_Сервер.ПолучитьНастройкиПользователя();
\tProvider_ApiKey = Настройки.Provider_ApiKey;
\tProvider_BaseUrl = Настройки.Provider_BaseUrl;
\tЗаполнитьСписокПровайдеров();
\tЕсли НЕ ЭтоРазрешенныйFreshПровайдер(Provider_BaseUrl) Тогда
\t\tProvider_BaseUrl = \"https://gitsell.ru/api/v1\";
\tКонецЕсли;
\tОбновитьВидимостьРегистрацииGitsell();"""
    if content.count(old) != 1:
        raise RuntimeError("Settings load block changed; Fresh provider adaptation needs update")
    content = content.replace(old, new)

    old = """&НаКлиенте
Процедура Provider_BaseUrlПриИзменении(Элемент)
\tОбновитьСписокМоделейПоАдресуСервера();
КонецПроцедуры"""
    new = """&НаСервере
Процедура ЗаполнитьСписокПровайдеров()
\tСписок = Элементы.Provider_BaseUrl.СписокВыбора;
\tСписок.Очистить();
\tСписок.Добавить(\"https://gitsell.ru/api/v1\", \"GitSell (рекомендуется)\");
\tСписок.Добавить(\"https://api.giga.chat/v1\", \"GigaChat\");
\tСписок.Добавить(\"https://ai.api.cloud.yandex.net/v1\", \"Yandex AI Studio\");
КонецПроцедуры

&НаСервере
Функция ЭтоРазрешенныйFreshПровайдер(URL)
\tВозврат URL = \"https://gitsell.ru/api/v1\"
\t\tИЛИ URL = \"https://api.giga.chat/v1\"
\t\tИЛИ URL = \"https://ai.api.cloud.yandex.net/v1\";
КонецФункции

&НаСервере
Процедура ОбновитьВидимостьРегистрацииGitsell()
\tЭлементы.ГруппаРегистрация.Видимость = Provider_BaseUrl = \"https://gitsell.ru/api/v1\";
КонецПроцедуры

&НаСервере
Процедура ПрименитьПровайдераНаСервере()
\tЕсли НЕ ЭтоРазрешенныйFreshПровайдер(Provider_BaseUrl) Тогда
\t\tProvider_BaseUrl = \"https://gitsell.ru/api/v1\";
\tКонецЕсли;
\tЕсли Provider_BaseUrl = \"https://gitsell.ru/api/v1\" Тогда
\t\tМодель = \"gpt-5.4-nano\";
\tИначеЕсли Provider_BaseUrl = \"https://api.giga.chat/v1\" Тогда
\t\tМодель = \"GigaChat-2-Pro\";
\tИначе
\t\tМодель = \"gpt://<идентификатор_каталога>/yandexgpt/latest\";
\tКонецЕсли;
\tОбновитьВидимостьРегистрацииGitsell();
\tЗаполнитьСписокМоделей();
КонецПроцедуры

&НаКлиенте
Процедура Provider_BaseUrlПриИзменении(Элемент)
\tПрименитьПровайдераНаСервере();
КонецПроцедуры"""
    if content.count(old) != 1:
        raise RuntimeError("Provider change handler changed; Fresh adaptation needs update")
    content = content.replace(old, new)

    save_marker = "\tЗапись.Provider_ApiKey = Provider_ApiKey;"
    save_guard = """\tЕсли НЕ ЭтоРазрешенныйFreshПровайдер(Provider_BaseUrl) Тогда
\t\tВызватьИсключение \"Для Fresh разрешены только GitSell, GigaChat и Yandex AI Studio.\";
\tКонецЕсли;

""" + save_marker
    if content.count(save_marker) != 1:
        raise RuntimeError("Settings save block changed; Fresh provider guard needs update")
    content = content.replace(save_marker, save_guard)
    write_text(path, content)


def adapt_fresh_provider_models(xml_root: Path) -> None:
    path = xml_root / GITSELL_MODULE
    content = read_text(path)
    old = """Функция ПолучитьСписокМоделейДляПровайдера(BaseUrl) Экспорт
\tЕсли ЭтоЛокальныйLLMProvider(BaseUrl) Тогда
\t\tВозврат Локальные_СписокМоделей();
\tКонецЕсли;
\tВозврат Gitsell_СписокМоделей();
КонецФункции"""
    new = """Функция ПолучитьСписокМоделейДляПровайдера(BaseUrl) Экспорт
\tЕсли BaseUrl = \"https://api.giga.chat/v1\" Тогда
\t\tМодели = Новый Массив;
\t\tМодели.Добавить(Новый Структура(\"id, name\", \"GigaChat-2\", \"GigaChat 2\"));
\t\tМодели.Добавить(Новый Структура(\"id, name\", \"GigaChat-2-Pro\", \"GigaChat 2 Pro\"));
\t\tМодели.Добавить(Новый Структура(\"id, name\", \"GigaChat-2-Max\", \"GigaChat 2 Max\"));
\t\tМодели.Добавить(Новый Структура(\"id, name\", \"GigaChat-3-Ultra\", \"GigaChat 3 Ultra\"));
\t\tВозврат Модели;
\tИначеЕсли BaseUrl = \"https://ai.api.cloud.yandex.net/v1\" Тогда
\t\tМодели = Новый Массив;
\t\tМодели.Добавить(Новый Структура(\"id, name\", \"gpt://<идентификатор_каталога>/yandexgpt/latest\", \"YandexGPT Pro (укажите идентификатор каталога)\"));
\t\tМодели.Добавить(Новый Структура(\"id, name\", \"gpt://<идентификатор_каталога>/yandexgpt-lite/latest\", \"YandexGPT Lite (укажите идентификатор каталога)\"));
\t\tВозврат Модели;
\tКонецЕсли;
\tВозврат Gitsell_СписокМоделей();
КонецФункции"""
    if content.count(old) != 1:
        raise RuntimeError("Provider model dispatcher changed; Fresh adaptation needs update")
    write_text(path, content.replace(old, new))


def adapt_fresh_provider_auth(xml_root: Path) -> None:
    path = xml_root / PROVIDERS_MODULE
    content = read_text(path)
    old = """\tЕсли НЕ ПустаяСтрока(Токен) Тогда
\t\tЗаголовки.Вставить(\"Authorization\", \"Bearer \" + Токен);
\tКонецЕсли;"""
    new = """\tЕсли СтрНайти(НРег(URLИзНастроек), \"api.giga.chat\") > 0 Тогда
\t\tТокенДоступа = ПолучитьFreshТокенGigaChat(Токен);
\t\tЕсли ПустаяСтрока(ТокенДоступа) Тогда
\t\t\tРезультат.ТипОтвета = \"Ошибка\";
\t\t\tРезультат.Текст = \"Не удалось получить токен доступа GigaChat. Проверьте Authorization Key.\";
\t\t\tВозврат Результат;
\t\tКонецЕсли;
\t\tЗаголовки.Вставить(\"Authorization\", \"Bearer \" + ТокенДоступа);
\tИначеЕсли СтрНайти(НРег(URLИзНастроек), \"cloud.yandex.net\") > 0 Тогда
\t\tЗаголовки.Вставить(\"Authorization\", \"Api-Key \" + Токен);
\tИначеЕсли НЕ ПустаяСтрока(Токен) Тогда
\t\tЗаголовки.Вставить(\"Authorization\", \"Bearer \" + Токен);
\tКонецЕсли;"""
    if content.count(old) != 1:
        raise RuntimeError("Authorization header block changed; Fresh adaptation needs update")
    content = content.replace(old, new)

    url_block = """\tЕсли ПустаяСтрока(URLИзНастроек) Тогда
\t\tURLИзНастроек = \"https://gitsell.ru/api/v1\";
\tКонецЕсли;"""
    guarded_url_block = url_block + """
\tЕсли URLИзНастроек <> \"https://gitsell.ru/api/v1\"
\t\tИ URLИзНастроек <> \"https://api.giga.chat/v1\"
\t\tИ URLИзНастроек <> \"https://ai.api.cloud.yandex.net/v1\" Тогда
\t\tРезультат.ТипОтвета = \"Ошибка\";
\t\tРезультат.Текст = \"Адрес ИИ-провайдера не разрешен в редакции для 1С:Фреш.\";
\t\tВозврат Результат;
\tКонецЕсли;"""
    if content.count(url_block) != 1:
        raise RuntimeError("Provider URL block changed; Fresh runtime allowlist needs update")
    content = content.replace(url_block, guarded_url_block)

    strategy_block = """\tСтратегияОтвета = ПостроитьСтратегиюОтвета(ПараметрыИИ, ОжидаемыйФормат);
\tДобавитьИнструментыВТелоЗапроса(ТелоЗапроса, ПараметрыИИ, ОжидаемыйФормат, СтратегияОтвета);
\tДобавитьРежимJSONВТелоЗапроса(ТелоЗапроса, ПараметрыИИ, ОжидаемыйФормат, СтратегияОтвета);"""
    adapted_strategy_block = strategy_block + """
\tЕсли СтрНайти(НРег(URLИзНастроек), \"api.giga.chat\") > 0 Тогда
\t\tАдаптироватьFreshЗапросGigaChat(ТелоЗапроса);
\tКонецЕсли;"""
    if content.count(strategy_block) != 1:
        raise RuntimeError("Response strategy block changed; GigaChat request adapter needs update")
    content = content.replace(strategy_block, adapted_strategy_block)

    response_anchor = "\t\tДанные = РезультатЗапроса.Данные;"
    response_replacement = response_anchor + """
\t\tЕсли СтрНайти(НРег(URLИзНастроек), \"api.giga.chat\") > 0 Тогда
\t\t\tАдаптироватьFreshОтветGigaChat(Данные);
\t\tКонецЕсли;"""
    if content.count(response_anchor) != 1:
        raise RuntimeError("Provider response block changed; GigaChat response adapter needs update")
    content = content.replace(response_anchor, response_replacement)

    anchor = "Функция ВызватьGitsellAiProxy(ТипСообщения, ТекстПользователя, История, ПараметрыИИ, СистемныйПромпт = \"\", Температура = Неопределено)"
    helper = """Процедура АдаптироватьFreshЗапросGigaChat(ТелоЗапроса)
\tЕсли ТелоЗапроса.Свойство(\"tools\") Тогда
\t\tФункции = Новый Массив;
\t\tДля Каждого Инструмент Из ТелоЗапроса.tools Цикл
\t\t\tЕсли ТипЗнч(Инструмент) = Тип(\"Структура\") И Инструмент.Свойство(\"function\") Тогда
\t\t\t\tЕсли Инструмент.function.Свойство(\"name\") И (Инструмент.function.name = \"submit_dsl\" ИЛИ Инструмент.function.name = \"submit_next_step\") Тогда
\t\t\t\t\tАдаптироватьFreshСхемуDSLGigaChat(Инструмент.function);
\t\t\t\tИначеЕсли Инструмент.function.Свойство(\"parameters\") Тогда
\t\t\t\t\tНормализоватьFreshСхемуGigaChat(Инструмент.function.parameters);
\t\t\t\tКонецЕсли;
\t\t\t\tФункции.Добавить(Инструмент.function);
\t\t\tКонецЕсли;
\t\tКонецЦикла;
\t\tТелоЗапроса.Удалить(\"tools\");
\t\tЕсли Функции.Количество() > 0 Тогда
\t\t\tТелоЗапроса.Вставить(\"functions\", Функции);
\t\tКонецЕсли;
\tКонецЕсли;
\tЕсли ТелоЗапроса.Свойство(\"tool_choice\") Тогда
\t\tВыбор = ТелоЗапроса.tool_choice;
\t\tТелоЗапроса.Удалить(\"tool_choice\");
\t\tЕсли ТипЗнч(Выбор) = Тип(\"Структура\") И Выбор.Свойство(\"function\") И Выбор.function.Свойство(\"name\") Тогда
\t\t\tТелоЗапроса.Вставить(\"function_call\", Новый Структура(\"name\", Выбор.function.name));
\t\tИначеЕсли Выбор = \"required\" Тогда
\t\t\tЕсли ТелоЗапроса.Свойство(\"functions\") И ТелоЗапроса.functions.Количество() = 1 Тогда
\t\t\t\tТелоЗапроса.Вставить(\"function_call\", Новый Структура(\"name\", ТелоЗапроса.functions[0].name));
\t\t\tИначе
\t\t\t\tТелоЗапроса.Вставить(\"function_call\", \"auto\");
\t\t\tКонецЕсли;
\t\tИначе
\t\t\tТелоЗапроса.Вставить(\"function_call\", Выбор);
\t\tКонецЕсли;
\tКонецЕсли;
КонецПроцедуры

Процедура АдаптироватьFreshСхемуDSLGigaChat(ФункцияGiga)
\tСвойства = Новый Структура;
\tОбязательные = Новый Массив;
\tЕсли ФункцияGiga.name = \"submit_next_step\" Тогда
\t\tСвойства.Вставить(\"step_id\", Новый Структура(\"type,description\", \"string\", \"Идентификатор текущего шага плана.\"));
\t\tОбязательные.Добавить(\"step_id\");
\tКонецЕсли;
\tСвойства.Вставить(\"dsl\", Новый Структура(\"type,description\", \"string\", \"Полный валидный JSON DSL-сценария: объект с dsl_version и массивом steps; каждый steps содержит action и параметры действия.\"));
\tОбязательные.Добавить(\"dsl\");
\tПараметры = Новый Структура;
\tПараметры.Вставить(\"type\", \"object\");
\tПараметры.Вставить(\"properties\", Свойства);
\tПараметры.Вставить(\"required\", Обязательные);
\tПараметры.Вставить(\"additionalProperties\", Ложь);
\tФункцияGiga.Вставить(\"parameters\", Параметры);
КонецПроцедуры

Процедура НормализоватьFreshСхемуGigaChat(Схема)
\tЕсли ТипЗнч(Схема) <> Тип(\"Структура\") Тогда
\t\tВозврат;
\tКонецЕсли;
\tТипСхемы = \"\";
\tЕсли Схема.Свойство(\"type\") Тогда
\t\tТипСхемы = НРег(Строка(Схема.type));
\tКонецЕсли;
\tЕсли ТипСхемы = \"object\" И НЕ Схема.Свойство(\"properties\") Тогда
\t\tСхема.Вставить(\"properties\", Новый Структура);
\tКонецЕсли;
\tЕсли Схема.Свойство(\"properties\") И ТипЗнч(Схема.properties) = Тип(\"Структура\") Тогда
\t\tДля Каждого СвойствоСхемы Из Схема.properties Цикл
\t\t\tНормализоватьFreshСхемуGigaChat(СвойствоСхемы.Значение);
\t\tКонецЦикла;
\tКонецЕсли;
\tЕсли Схема.Свойство(\"items\") Тогда
\t\tНормализоватьFreshСхемуGigaChat(Схема.items);
\tКонецЕсли;
КонецПроцедуры

Процедура АдаптироватьFreshОтветGigaChat(Данные)
\tЕсли НЕ Данные.Свойство(\"choices\") Тогда
\t\tВозврат;
\tКонецЕсли;
\tДля Каждого Вариант Из Данные.choices Цикл
\t\tЕсли НЕ Вариант.Свойство(\"message\") ИЛИ НЕ Вариант.message.Свойство(\"function_call\") Тогда
\t\t\tПродолжить;
\t\tКонецЕсли;
\t\tВызовФункции = Вариант.message.function_call;
\t\tЕсли НЕ ВызовФункции.Свойство(\"name\") Тогда
\t\t\tПродолжить;
\t\tКонецЕсли;
\t\tАргументы = \"{}\";
\t\tЕсли ВызовФункции.Свойство(\"arguments\") Тогда
\t\t\tАргументыGiga = ПодготовитьFreshАргументыGigaChat(ВызовФункции.name, ВызовФункции.arguments);
\t\t\tЕсли ТипЗнч(АргументыGiga) = Тип(\"Строка\") Тогда
\t\t\t\tАргументы = АргументыGiga;
\t\t\tИначе
\t\t\t\tЗапись = Новый ЗаписьJSON;
\t\t\t\tЗапись.УстановитьСтроку();
\t\t\t\tЗаписатьJSON(Запись, АргументыGiga);
\t\t\t\tАргументы = Запись.Закрыть();
\t\t\tКонецЕсли;
\t\tКонецЕсли;
\t\tФункцияOpenAI = Новый Структура(\"name,arguments\", ВызовФункции.name, Аргументы);
\t\tToolCall = Новый Структура(\"id,type,function\", Строка(Новый УникальныйИдентификатор), \"function\", ФункцияOpenAI);
\t\tToolCalls = Новый Массив;
\t\tToolCalls.Добавить(ToolCall);
\t\tВариант.message.Вставить(\"tool_calls\", ToolCalls);
\t\tВариант.Вставить(\"finish_reason\", \"tool_calls\");
\tКонецЦикла;
КонецПроцедуры

Функция ПодготовитьFreshАргументыGigaChat(ИмяФункции, Аргументы)
\tЕсли (ИмяФункции <> \"submit_next_step\" И ИмяФункции <> \"submit_dsl\") ИЛИ ТипЗнч(Аргументы) <> Тип(\"Структура\") ИЛИ НЕ Аргументы.Свойство(\"dsl\") Тогда
\t\tВозврат Аргументы;
\tКонецЕсли;
\tПопытка
\t\tЧтение = Новый ЧтениеJSON;
\t\tЧтение.УстановитьСтроку(Аргументы.dsl);
\t\tDSLОбъект = ПрочитатьJSON(Чтение);
\t\tЕсли ТипЗнч(DSLОбъект) = Тип(\"Структура\") И Аргументы.Свойство(\"step_id\") Тогда
\t\t\tDSLОбъект.Вставить(\"step_id\", Аргументы.step_id);
\t\tКонецЕсли;
\t\tВозврат DSLОбъект;
\tИсключение
\t\tВозврат Аргументы;
\tКонецПопытки;
КонецФункции

Функция ПолучитьFreshТокенGigaChat(КлючАвторизации)
\tПопытка
\t\tСоединение = Новый HTTPСоединение(\"ngw.devices.sberbank.ru\", 9443, , , , 30, Новый ЗащищенноеСоединениеOpenSSL());
\t\tЗаголовки = Новый Соответствие;
\t\tЗаголовки.Вставить(\"Content-Type\", \"application/x-www-form-urlencoded\");
\t\tЗаголовки.Вставить(\"Accept\", \"application/json\");
\t\tЗаголовки.Вставить(\"RqUID\", Строка(Новый УникальныйИдентификатор));
\t\tЗаголовки.Вставить(\"Authorization\", \"Basic \" + КлючАвторизации);
\t\tОбласти = Новый Массив;
\t\tОбласти.Добавить(\"GIGACHAT_API_PERS\");
\t\tОбласти.Добавить(\"GIGACHAT_API_B2B\");
\t\tОбласти.Добавить(\"GIGACHAT_API_CORP\");
\t\tДля Каждого ОбластьДоступа Из Области Цикл
\t\t\tЗапрос = Новый HTTPЗапрос(\"/api/v2/oauth\", Заголовки);
\t\t\tЗапрос.УстановитьТелоИзСтроки(\"scope=\" + ОбластьДоступа, КодировкаТекста.UTF8, ИспользованиеByteOrderMark.НеИспользовать);
\t\t\tОтвет = Соединение.ОтправитьДляОбработки(Запрос);
\t\t\tЕсли Ответ.КодСостояния = 200 Тогда
\t\t\t\tЧтение = Новый ЧтениеJSON;
\t\t\t\tЧтение.УстановитьСтроку(Ответ.ПолучитьТелоКакСтроку());
\t\t\t\tДанные = ПрочитатьJSON(Чтение);
\t\t\t\tЕсли Данные.Свойство(\"access_token\") Тогда
\t\t\t\t\tВозврат Данные.access_token;
\t\t\t\tКонецЕсли;
\t\t\tКонецЕсли;
\t\tКонецЦикла;
\tИсключение
\t\tВозврат \"\";
\tКонецПопытки;
\tВозврат \"\";
КонецФункции

""" + anchor
    if content.count(anchor) != 1:
        raise RuntimeError("AI proxy routine anchor changed; Fresh GigaChat helper needs update")
    content = content.replace(anchor, helper)
    write_text(path, content)


def audit_preflight(xml_root: Path) -> None:
    findings: list[str] = []
    for path in xml_root.rglob("*.bsl"):
        lowered = read_text(path).lower()
        for marker, reason in FORBIDDEN_FRESH_MARKERS.items():
            if marker in lowered:
                findings.append(f"{path.relative_to(xml_root)}: {reason} ({marker})")
        if re.search(r"новый\s+записьтекста\s*\([^\r\n]*путьклогуотладки", lowered):
            findings.append(f"{path.relative_to(xml_root)}: arbitrary server-side debug log write")
    if findings:
        raise RuntimeError("Fresh audit preflight failed:\n  " + "\n  ".join(findings))

    providers = read_text(xml_root / PROVIDERS_MODULE).lower()
    for host in FRESH_ALLOWED_EXTERNAL_HOSTS:
        if host not in providers and host not in read_text(xml_root / GITSELL_MODULE).lower():
            raise RuntimeError(f"Fresh external host is not represented in prepared code: {host}")


def prepare_source(source: Path, destination: Path) -> None:
    if destination.exists():
        shutil.rmtree(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, destination)
    remove_self_update(destination)
    remove_server_debug_file_log(destination)
    adapt_fresh_provider_form(destination)
    adapt_fresh_provider_models(destination)
    adapt_fresh_provider_auth(destination)
    audit_preflight(destination)


def designer_args(connection_string: str, server: str, ref: str, user: str, password: str) -> list[str]:
    args = ["DESIGNER", "/DisableStartupDialogs", "/DisableStartupMessages"]
    if server and ref:
        args.extend(["/S", f"{server}\\{ref}"])
    elif connection_string:
        args.extend(["/IBConnectionString", connection_string])
    else:
        raise RuntimeError("FRESH_1C_SERVER/FRESH_1C_REF or FRESH_1C_CONNECTION_STRING is required for --build")
    if user:
        args.extend(["/N", user])
    if password:
        args.extend(["/P", password])
    return args


def run_1c(executable: Path, args: list[str]) -> None:
    result = subprocess.run([str(executable), *args], timeout=600, check=False)
    if result.returncode:
        raise RuntimeError(f"1C exited with code {result.returncode}")


def build_cfe(
    prepared: Path,
    output: Path,
    connection_string: str,
    server: str,
    ref: str,
    user: str,
    password: str,
    platform: Path,
) -> None:
    if not platform.is_file():
        raise RuntimeError(f"1cv8 executable not found: {platform}")
    output.parent.mkdir(parents=True, exist_ok=True)
    log_dir = PROJECT_ROOT / "automation" / "build" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    base = designer_args(connection_string, server, ref, user, password)
    load_log = log_dir / "fresh_build_load.log"
    dump_log = log_dir / "fresh_build_dump.log"
    run_1c(platform, base + ["/Out", str(load_log), "/LoadConfigFromFiles", str(prepared), "-Extension", EXTENSION_NAME])
    if output.exists():
        output.unlink()
    run_1c(platform, base + ["/Out", str(dump_log), "/DumpCfg", str(output), "-Extension", EXTENSION_NAME])
    if not output.is_file():
        raise RuntimeError(f"CFE was not created: {output}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare/build the audit-safe 1C:Fresh CFE edition")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--prepare-only", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--connection-string", default=os.getenv("FRESH_1C_CONNECTION_STRING", ""))
    parser.add_argument("--server", default=os.getenv("FRESH_1C_SERVER", ""))
    parser.add_argument("--ref", default=os.getenv("FRESH_1C_REF", ""))
    parser.add_argument("--user", default=os.getenv("FRESH_1C_USER", ""))
    parser.add_argument("--password", default=os.getenv("FRESH_1C_PASSWORD", ""))
    parser.add_argument("--platform", type=Path, default=Path(os.getenv("PLATFORM_85", "")))
    args = parser.parse_args()

    prepare_source(args.source.resolve(), args.prepared.resolve())
    print(f"Fresh XML prepared: {args.prepared.resolve()}")
    if args.prepare_only and not args.build:
        return 0
    if not args.build:
        print("Preparation complete. Pass --build to create CFE.")
        return 0
    build_cfe(
        args.prepared.resolve(),
        args.output.resolve(),
        args.connection_string,
        args.server,
        args.ref,
        args.user,
        args.password,
        args.platform.resolve(),
    )
    print(f"Fresh CFE built: {args.output.resolve()}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
