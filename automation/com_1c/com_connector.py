# -*- coding: utf-8 -*-
"""
Модуль для работы с базой данных 1С через COM.

Содержит:
- выбор и инициализация COM-коннектора (V83.COMConnector / V82.COMConnector);
- построение строки подключения;
- выполнение запросов и безопасная работа с COM-объектами.
"""

import re
import sys
from typing import Iterable, Optional, Sequence, Tuple


def setup_console_encoding():
    """Настраивает кодировку stdout/stderr для корректного вывода кириллицы в Windows."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        # Переключаем консоль на UTF-8 (65001)
        kernel32.SetConsoleOutputCP(65001)
        kernel32.SetConsoleCP(65001)
    except Exception:
        pass
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

try:
    import win32com.client
except ImportError:
    win32com = None  # type: ignore

DEFAULT_COM_PROGIDS: Tuple[str, ...] = (
    "V85.COMConnector",  # платформа 8.5
    "V83.COMConnector",  # платформа 8.3
    "V82.COMConnector",  # платформа 8.2
)

_verbose = False


def set_verbose(value: bool) -> None:
    """Включить/выключить вывод отладочных сообщений."""
    global _verbose
    _verbose = value


def _log(msg: str) -> None:
    if _verbose:
        print(msg)


def call_if_callable(value, *args, **kwargs):
    """Вызывает объект, если он вызваемый, иначе возвращает как есть."""
    if value is None:
        return None
    if win32com and isinstance(value, win32com.client.CDispatch):
        return value
    if callable(value):
        try:
            return value(*args, **kwargs)
        except Exception:
            return None
    return value


def safe_getattr(obj, attr_name: str, default=None):
    """Безопасно получает атрибут COM-объекта."""
    if obj is None:
        return default
    try:
        return getattr(obj, attr_name)
    except Exception:
        return default


def _xml_type_name(com_object, value) -> str:
    type_info = None
    xml_type_method = safe_getattr(com_object, "XMLТип", None)
    if callable(xml_type_method):
        try:
            type_info = xml_type_method(value)
        except Exception:
            type_info = None
    if type_info is None:
        xml_type_value_method = safe_getattr(com_object, "XMLТипЗнч", None)
        if callable(xml_type_value_method):
            try:
                type_info = xml_type_value_method(value)
            except Exception:
                type_info = None
    type_info = call_if_callable(type_info)
    if type_info is None:
        return ""
    name = safe_getattr(type_info, "ИмяТипа", None)
    name = call_if_callable(name)
    if not name:
        name = safe_getattr(type_info, "Имя", None)
        name = call_if_callable(name)
    if not name:
        name = safe_getattr(type_info, "Name", None)
        name = call_if_callable(name)
    if name:
        try:
            name_str = str(name)
        except Exception:
            name_str = None
        if name_str:
            for old, new in (("CatalogRef.", "Справочник."), ("EnumRef.", "Перечисление.")):
                if name_str.startswith(old):
                    name_str = name_str.replace(old, new, 1)
            return name_str
    try:
        return "" if type_info is None else str(type_info)
    except Exception:
        return ""


def _stringify_query_value(com_object, value, column_name: str) -> str:
    if value is None:
        return ""
    if column_name.endswith("_Тип"):
        type_name = _xml_type_name(com_object, value)
        if type_name:
            return type_name
    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        try:
            y, m, d = int(value.year), int(value.month), int(value.day)
            if hasattr(value, "hour") and hasattr(value, "minute"):
                h = int(value.hour)
                mi = int(value.minute)
                s = int(value.second) if hasattr(value, "second") else 0
                return f"{y:04d}-{m:02d}-{d:02d} {h:02d}:{mi:02d}:{s:02d}"
            return f"{y:04d}-{m:02d}-{d:02d}"
        except (ValueError, AttributeError, TypeError):
            pass
    if hasattr(value, "_oleobj_"):
        try:
            text_value = str(value)
        except Exception:
            text_value = ""
        if text_value and "<COMObject" not in text_value:
            return text_value
        if column_name.endswith("_Тип"):
            return _xml_type_name(com_object, value)
        return ""
    try:
        return str(value)
    except Exception:
        return ""


def get_com_connector(progids: Optional[Sequence[str]] = None):
    """
    Инициализирует COM-коннектор 1С, перебирая переданные ProgID.
    Возвращает кортеж (коннектор, использованный ProgID) или возбуждает исключение.
    """
    if win32com is None:
        raise RuntimeError(
            "Модуль pywin32 не установлен. Установите: pip install pywin32"
        )
    try:
        import pythoncom
        try:
            pythoncom.CoInitialize()
        except pythoncom.com_error as e:
            if getattr(e, "hresult", None) != -2147221008:
                raise
    except ImportError:
        pass
    except Exception:
        pass

    errors = []
    for progid in progids or DEFAULT_COM_PROGIDS:
        try:
            connector = win32com.client.Dispatch(progid)
            _log(f"Используется COM-коннектор: {progid}")
            return connector, progid
        except Exception as exc:
            errors.append((progid, exc))
    messages = "; ".join(f"{pid}: {err}" for pid, err in errors)
    raise RuntimeError(f"Не удалось создать COM-коннектор. Детали: {messages}")


def _get_short_path(path: str) -> Optional[str]:
    """
    Преобразует путь в короткий формат 8.3 (обход проблем с кириллицей в 1С COM).
    Возвращает None при ошибке.
    """
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.windll.kernel32
        buf = ctypes.create_unicode_buffer(wintypes.MAX_PATH)
        if kernel32.GetShortPathNameW(path, buf, len(buf)):
            return buf.value
    except Exception:
        pass
    return None


def _apply_short_path_for_unicode(connection_string: str) -> str:
    """
    Заменяет путь в File="..." на короткий (8.3), если путь содержит не-ASCII.
    Обход проблем с кириллицей в путях при подключении 1С через COM.
    """
    match = re.search(r'File="([^"]*)"', connection_string)
    if not match:
        return connection_string
    path = match.group(1).rstrip("\\")
    if not path or not any(ord(c) > 127 for c in path):
        return connection_string
    short_path = _get_short_path(path)
    if short_path:
        old_part = match.group(0)
        new_part = f'File="{short_path}"'
        connection_string = connection_string.replace(old_part, new_part, 1)
        _log(f"Путь с кириллицей заменён на короткий: {short_path}")
    return connection_string


def resolve_connection_string(db_path_or_config: str) -> Tuple[str, str]:
    """
    Определяет строку подключения к базе 1С.
    Возвращает кортеж (connection_string, human_readable_name).
    """
    if "Srvr=" in db_path_or_config or "Ref=" in db_path_or_config:
        return db_path_or_config, "Строка подключения (сервер)"
    if 'File="' in db_path_or_config and ";" in db_path_or_config.split("File=", 1)[-1]:
        connection_string = db_path_or_config
    else:
        connection_string = f'File="{db_path_or_config}";Usr=;Pwd=;'
    connection_string = _apply_short_path_for_unicode(connection_string)
    return connection_string, f"Файловая база: {db_path_or_config}"


def connect_to_1c(db_path_or_config: str):
    """
    Подключается к базе данных 1С через COM.

    Args:
        db_path_or_config: строка подключения или путь к файловой базе.

    Returns:
        COM-объект соединения или None при ошибке.
    """
    try:
        connector, progid = get_com_connector()
    except Exception as exc:
        print(f"Ошибка создания COM-коннектора: {exc}")
        print("Убедитесь, что установлена платформа 1С:Предприятие.")
        return None
    try:
        connection_string, description = resolve_connection_string(db_path_or_config)
        _log(f"Подключение: {description}")
    except Exception as exc:
        print(f"Ошибка подготовки строки подключения: {exc}")
        return None
    try:
        com_object = connector.Connect(connection_string)
        _log("Подключение успешно.")
        return com_object
    except Exception as exc:
        print(f"Ошибка подключения к базе ({progid}): {exc}")
        print("Возможные причины: база занята (закройте 1С:Предприятие), неверный путь или нет прав.")
        return None


def create_query(com_object, query_text: str):
    """Создаёт объект запроса 1С с переданным текстом."""
    query = com_object.NewObject("Запрос")
    query.Текст = query_text
    return query


def execute_query(
    com_object,
    query_text: str,
    column_names: Iterable[str],
    params: Optional[dict] = None,
) -> list:
    """
    Выполняет запрос 1С и возвращает данные в виде списка словарей.
    """
    query = create_query(com_object, query_text)
    if params:
        for name, value in params.items():
            query.УстановитьПараметр(name, value)
    result = query.Выполнить()
    selection = result.Выбрать()
    rows = []
    col_list = list(column_names)
    getter = safe_getattr(selection, "Получить", None)
    get_item = safe_getattr(selection, "__getitem__", None)

    while selection.Следующий():
        row_dict = {}
        for column_name in col_list:
            value = safe_getattr(selection, column_name, None)
            if callable(value) and not (win32com and isinstance(value, win32com.client.CDispatch)):
                value = None
            if value is None and callable(getter):
                try:
                    value = getter(column_name)
                except Exception:
                    value = None
            if value is None and callable(get_item):
                try:
                    value = get_item(column_name)
                except Exception:
                    value = None
            row_dict[column_name] = _stringify_query_value(com_object, value, column_name)
        rows.append(row_dict)
    return rows
