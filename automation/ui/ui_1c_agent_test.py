# -*- coding: utf-8 -*-
"""
Desktop UI тест формы ИИ агента без Vanessa и без COM.

Сценарий:
1. Открыть клиент 1С.
2. Открыть именно форму "ИИ Агент".
3. Нажать "Новый диалог".
4. Ввести пользовательское сообщение в поле ввода.
5. Нажать кнопку "Отправить".
6. Дождаться ожидаемого текста в чате или статусе.
"""

from __future__ import annotations

import argparse
import csv
import ctypes
import importlib.util
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
HOST_PREPARED_QUERY1C_MARKER = "__HOST_PREPARED_QUERY1C__"
DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'
DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

try:
    from com_1c import call_procedure, connect_to_1c, get_enum_value
except ModuleNotFoundError:
    _com_package_root = AUTOMATION_ROOT / "com_1c"
    _com_init = _com_package_root / "__init__.py"
    _spec = importlib.util.spec_from_file_location(
        "com_1c",
        _com_init,
        submodule_search_locations=[str(_com_package_root)],
    )
    if _spec is None or _spec.loader is None:
        raise
    _module = importlib.util.module_from_spec(_spec)
    sys.modules["com_1c"] = _module
    _spec.loader.exec_module(_module)
    call_procedure = _module.call_procedure
    connect_to_1c = _module.connect_to_1c
    get_enum_value = _module.get_enum_value


def _parse_1c_connection_string(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, raw in re.findall(r"([A-Za-zА-Яа-я0-9_]+)\s*=\s*(\"(?:[^\"]|\"\")*\"|[^;]*)\s*;?", value or ""):
        item = raw.strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1].replace('""', '"')
        result[key.lower()] = item
    return result


def _enterprise_connection_args(base_path: str) -> list[str]:
    parts = _parse_1c_connection_string(base_path)
    if "srvr" in parts and "ref" in parts:
        return ["/S", f"{parts['srvr']}\\{parts['ref']}"]
    if "file" in parts:
        return ["/F", parts["file"]]
    return ["/F", base_path]


def _com_connection_string(base_path: str, user: str, password: str) -> str:
    parts = _parse_1c_connection_string(base_path)
    if parts:
        parts["usr"] = user
        parts["pwd"] = password
        ordered_keys = ["file", "srvr", "ref", "usr", "pwd"]
        keys = [key for key in ordered_keys if key in parts] + [
            key for key in parts if key not in ordered_keys
        ]
        names = {
            "file": "File",
            "srvr": "Srvr",
            "ref": "Ref",
            "usr": "Usr",
            "pwd": "Pwd",
        }
        return "".join(f'{names.get(key, key)}="{parts[key]}";' for key in keys)
    return f'File="{base_path}";Usr="{user}";Pwd="{password}";'


def setup_console_encoding() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        ctypes.windll.kernel32.SetConsoleCP(65001)
        ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    except Exception:
        pass
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


try:
    from pywinauto import Application, Desktop, keyboard, mouse
except Exception:
    print(
        "Ошибка: не импортирован pywinauto. Установите зависимости:\n"
        "pip install -r automation\\ui\\requirements-ui.txt",
        file=sys.stderr,
    )
    raise


@dataclass
class UiConfig:
    platform_exe: str
    base_path: str
    user: str
    password: str
    prompt: str
    followups: list[str]
    show_query_between_turns: bool
    mouse_control: bool
    dialog_type: str
    expected_text: str
    timeout_sec: int
    startup_timeout_sec: int
    backend: str
    log_file: Optional[str]
    screenshot_dir: Optional[str]
    leave_open: bool
    approval_action: str
    require_approval: bool
    test_case: str
    query_text: str
    query_params_json: str
    web_url: str
    chrome_exe: str
    headed: bool
    skip_com_prepare: bool
    record_start_marker: str


class Logger:
    def __init__(self, log_file: Optional[str]) -> None:
        self._path = Path(log_file) if log_file else None
        if self._path:
            self._path.parent.mkdir(parents=True, exist_ok=True)

    def info(self, message: str) -> None:
        line = f"[INFO] {message}"
        print(line)
        if self._path:
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")

    def error(self, message: str) -> None:
        line = f"[ERROR] {message}"
        print(line, file=sys.stderr)
        if self._path:
            with self._path.open("a", encoding="utf-8") as stream:
                stream.write(line + "\n")


class OneCAgentUiTest:
    def __init__(self, config: UiConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.process: Optional[subprocess.Popen[str]] = None
        self.app: Optional[Application] = None
        self.main_window = None
        self.approval_seen = False
        self.com_connection = None
        self.prepared_dialog_ref = None
        self.client_pids: list[int] = []
        self.client_image_name = ""

    def run(self) -> int:
        try:
            self.logger.info(
                "Параметры сценария: dialog_type={!r}, followups={}, show_query_between_turns={}, mouse_control={}.".format(
                    self.config.dialog_type,
                    len(self.config.followups),
                    self.config.show_query_between_turns,
                    self.config.mouse_control,
                )
            )
            skip_com_prepare = self.config.skip_com_prepare or HOST_PREPARED_QUERY1C_MARKER in self.config.prompt
            if self.config.test_case == "query1c_form" and not skip_com_prepare:
                self._prepare_query1c_dialog_via_com()
            self._start_client()
            self._open_agent_form()
            if self.config.test_case == "query1c_form":
                self._run_query1c_form_scenario()
            else:
                self._start_new_dialog()
                self._select_dialog_type()
                self._signal_recording_start()
                self._enter_prompt()
                baseline_success_count = self._success_marker_count()
                self._send_prompt()
                self._wait_expected_response(baseline_success_count)
                if self.config.show_query_between_turns:
                    self._show_query_form_preview()
                for followup in self.config.followups:
                    self.logger.info(f"Отправляем follow-up: {followup!r}")
                    self.config.prompt = followup
                    self._enter_prompt()
                    baseline_success_count = self._success_marker_count()
                    self._send_prompt()
                    self._wait_expected_response(baseline_success_count)
                    if self.config.show_query_between_turns:
                        self._show_query_form_preview()
            if self.config.require_approval and not self.approval_seen:
                raise RuntimeError("Сценарий требовал ручного подтверждения, но pending approval в UI не появился.")
            self.logger.info("UI тест завершён успешно.")
            return 0
        except Exception as exc:
            self.logger.error(str(exc))
            self._capture_debug_artifacts()
            return 1
        finally:
            if not self.config.leave_open:
                self._close_client()

    def _start_client(self) -> None:
        client_env = os.environ.copy()
        self._clear_proxy_env(client_env)
        image_name = Path(self.config.platform_exe).name
        self.client_image_name = image_name
        before_pids = set(self._list_process_ids(image_name))
        cmd = [
            self.config.platform_exe,
            "ENTERPRISE",
            "/DisableStartupDialogs",
            "/DisableStartupMessages",
            *_enterprise_connection_args(self.config.base_path),
            "/N",
            self.config.user,
        ]
        if self.config.password:
            cmd.extend(["/P", self.config.password])
        startup_log = self._startup_log_path()
        if startup_log:
            cmd.extend(["/Out", startup_log, "-NoTruncate"])
        self.logger.info("Запуск клиента 1С.")
        self.process = subprocess.Popen(cmd, env=client_env, cwd=str(Path(self.config.platform_exe).parent))
        self.client_pids = self._wait_for_client_processes(image_name, before_pids)
        self.main_window = self._wait_for_top_window(self.client_pids)
        self.app = Application(backend=self.config.backend).connect(
            process=self.main_window.process_id(),
            timeout=self.config.startup_timeout_sec,
        )
        self.main_window.set_focus()
        self.logger.info(f"Подключились к окну: {self.main_window.window_text()!r}")

    def _wait_for_client_processes(self, image_name: str, before_pids: set[int]) -> list[int]:
        deadline = time.time() + self.config.startup_timeout_sec
        while time.time() < deadline:
            current_pids = self._list_process_ids(image_name)
            new_pids = [pid for pid in current_pids if pid not in before_pids]
            if new_pids:
                self.logger.info(f"Новые процессы клиента: {new_pids}")
                return new_pids
            if self.process and self.process.poll() is not None:
                return [self.process.pid]
            time.sleep(1)
        return [self.process.pid] if self.process else []

    def _startup_log_path(self) -> str:
        if self.config.log_file:
            return str(Path(self.config.log_file).with_name("desktop_1c_startup.log").resolve())
        if self.config.screenshot_dir:
            return str((Path(self.config.screenshot_dir).parent / "desktop_1c_startup.log").resolve())
        return ""

    def _wait_for_top_window(self, process_ids: list[int]):
        deadline = time.time() + self.config.startup_timeout_sec
        while time.time() < deadline:
            if self.client_image_name:
                for pid in self._list_process_ids(self.client_image_name):
                    if pid not in process_ids:
                        process_ids.append(pid)
            visible = []
            for win in Desktop(backend=self.config.backend).windows():
                try:
                    if process_ids and win.process_id() not in process_ids:
                        continue
                    if self._safe_is_visible(win):
                        visible.append(win)
                except Exception:
                    continue
            if visible:
                visible.sort(key=lambda w: len(self._safe_text(w)), reverse=True)
                return visible[0]
            self._raise_if_error_dialog()
            time.sleep(1)
        self.logger.info(f"Окна процессов клиента перед падением: {self._collect_process_windows(process_ids)}")
        raise RuntimeError("Не удалось дождаться главного окна 1С.")

    def _list_process_ids(self, image_name: str) -> list[int]:
        try:
            output = subprocess.check_output(
                ["tasklist", "/FO", "CSV", "/NH", "/FI", f"IMAGENAME eq {image_name}"],
                text=True,
                encoding="cp866",
                errors="replace",
            )
        except Exception:
            return []
        process_ids: list[int] = []
        for row in csv.reader(output.splitlines()):
            if len(row) < 2:
                continue
            if row[0].strip('"').lower() != image_name.lower():
                continue
            try:
                process_ids.append(int(row[1].strip('"')))
            except ValueError:
                continue
        return process_ids

    def _collect_process_windows(self, process_ids: list[int]) -> list[dict[str, object]]:
        windows_info: list[dict[str, object]] = []
        for win in Desktop(backend=self.config.backend).windows():
            try:
                pid = win.process_id()
                if process_ids and pid not in process_ids:
                    continue
                windows_info.append(
                    {
                        "pid": pid,
                        "title": win.window_text(),
                        "visible": self._safe_is_visible(win),
                        "class_name": win.class_name(),
                    }
                )
            except Exception:
                continue
        return windows_info

    def _open_agent_form(self) -> None:
        self.logger.info("Открываем раздел 'ИИ Агент'.")
        self._wait_until_client_ready(60)
        nav_item = self._find_descendant_exact("ИИ Агент", "TabItem", 20)
        self._open_agent_section(nav_item)
        if self._window_contains_any(["Текущий диалог", "Новый диалог", "Отправить"]):
            self.logger.info("Форма агента уже открыта.")
            return
        agent_entry = self._find_descendant_by_titles(
            ["ИИ Агент"],
            ["MenuItem", "Hyperlink", "Text", "ListItem"],
            20,
        )
        self._click(agent_entry)
        self._wait_agent_form_ready(30)
        self.logger.info("Форма агента открыта.")

    def _start_new_dialog(self) -> None:
        self.logger.info("Создаём новый диалог в форме агента.")
        button = self._find_descendant_by_titles(["Новый диалог", "New dialog"], ["Button"], 20)
        self._click(button)
        self._wait_window_text_contains("Готов к работе", 20)

    def _select_dialog_type(self) -> None:
        target_variants = self._dialog_type_variants(self.config.dialog_type)
        if not target_variants:
            return
        target = target_variants[0]
        try:
            combo = self._locate_dialog_type_combo()
        except Exception:
            self.logger.info("Не удалось найти selector типа диалога, оставляем текущий режим.")
            return
        current = self._safe_text(combo).strip()
        if current and self._normalize_dialog_type(current) == self._normalize_dialog_type(target):
            return
        self.logger.info(f"Выбираем тип диалога: {target!r}.")
        if self.config.mouse_control and self._try_select_dialog_type_via_mouse(combo, target):
            return
        if self._try_select_dialog_type_via_wrapper(combo, target):
            return
        self._click(combo)
        time.sleep(0.5)
        try:
            option = self._find_descendant_by_titles(target_variants, ["ListItem", "MenuItem", "Text", "Custom"], 10)
            self._click(option)
            time.sleep(0.7)
        except Exception:
            self.logger.info("Не нашли popup-элемент типа диалога, пробуем клавиатурный fallback.")
        if self._dialog_type_is_active(target):
            return
        if self._try_select_dialog_type_via_text_input(combo, target_variants):
            return
        if self._try_select_dialog_type_via_dropdown_keyboard(combo, target):
            return
        self._click(combo)
        time.sleep(0.3)
        self._try_select_dialog_type_via_keyboard(target)
        time.sleep(0.7)
        if not self._dialog_type_is_active(target):
            if self._normalize_dialog_type(target) == "запрос1с" and not self._safe_text(combo).strip():
                self.logger.info("UIA не читает выбранное значение selector, продолжаем после визуального выбора Запрос 1С.")
                return
            raise RuntimeError(f"Не удалось переключить тип диалога на {target!r}.")

    def _try_select_dialog_type_via_mouse(self, combo, target: str) -> bool:
        rect = combo.rectangle()
        option_offsets = (34, 58, 82)
        arrow = (rect.right - 10, rect.top + rect.height() // 2)
        self.logger.info("Mouse-control: выбираем тип диалога через раскрытие combo на экране.")
        for offset in option_offsets:
            try:
                self._activate_main_window()
                self._click_at(arrow)
                time.sleep(0.5)
                self._click_at((rect.left + max(30, rect.width() // 2), rect.bottom + offset))
                time.sleep(0.8)
                if self._dialog_type_is_active(target):
                    return True
            except Exception as exc:
                self.logger.info(f"Mouse-control выбор типа диалога не сработал: {exc}")
        return False

    def _try_select_dialog_type_via_text_input(self, combo, target_variants: list[str]) -> bool:
        for target in target_variants:
            try:
                self.logger.info(f"Пробуем ввести тип диалога через clipboard: {target!r}.")
                self._click(combo)
                time.sleep(0.2)
                keyboard.send_keys("^a", pause=0.05)
                keyboard.send_keys("{BACKSPACE}", pause=0.05)
                self._paste_text_to_active_window(target)
                time.sleep(0.3)
                keyboard.send_keys("{ENTER}", pause=0.05)
                time.sleep(0.7)
                if self._dialog_type_is_active(target):
                    return True
                keyboard.send_keys("{TAB}", pause=0.05)
                time.sleep(0.5)
                if self._dialog_type_is_active(target):
                    return True
            except Exception as exc:
                self.logger.info(f"Ввод типа диалога через clipboard не сработал: {exc}")
        return False

    def _try_select_dialog_type_via_dropdown_keyboard(self, combo, target: str) -> bool:
        rect = combo.rectangle()
        click_points = [
            (rect.right - 10, rect.top + rect.height() // 2),
            (rect.left + rect.width() // 2, rect.top + rect.height() // 2),
        ]
        sequences = (
            "{F4}{DOWN}{ENTER}",
            "%{DOWN}{DOWN}{ENTER}",
            "{DOWN}{ENTER}",
            "{DOWN}{DOWN}{ENTER}",
            "{UP}{ENTER}",
        )
        for point in click_points:
            for sequence in sequences:
                try:
                    self.logger.info(f"Пробуем раскрыть selector типа диалога клавиатурой: {sequence!r}.")
                    self._click_at(point)
                    time.sleep(0.3)
                    keyboard.send_keys(sequence, pause=0.08)
                    time.sleep(0.8)
                    if self._dialog_type_is_active(target):
                        return True
                except Exception as exc:
                    self.logger.info(f"Клавиатурный dropdown fallback не сработал: {exc}")
        return False

    def _normalize_dialog_type(self, value: str) -> str:
        normalized = (value or "").strip().lower().replace(" ", "")
        mapping = {
            "agent": "агент",
            "агент": "агент",
            "запрос1с": "запрос1с",
            "zapros1s": "запрос1с",
        }
        return mapping.get(normalized, normalized)

    def _dialog_type_variants(self, value: str) -> list[str]:
        normalized = self._normalize_dialog_type(value)
        if normalized == "агент":
            return ["Агент", "Agent"]
        if normalized == "запрос1с":
            return ["Запрос 1С", "Запрос1С", "Zapros1S"]
        raw = (value or "").strip()
        return [raw] if raw else []

    def _locate_dialog_type_combo(self):
        candidates = []
        for item in self._iter_descendants():
            if self._safe_control_type(item) != "ComboBox":
                continue
            rect = item.rectangle()
            if rect.width() < 120 or rect.height() < 18:
                continue
            if rect.left < 900 or rect.top < 70 or rect.top > 170:
                continue
            candidates.append(item)
        if not candidates:
            raise RuntimeError("Не найден selector типа диалога.")
        candidates.sort(key=lambda item: (item.rectangle().left, -abs(item.rectangle().top - 110)), reverse=True)
        return candidates[0]

    def _try_select_dialog_type_via_wrapper(self, combo, target: str) -> bool:
        for method_name in ("select", "select_item"):
            method = getattr(combo, method_name, None)
            if method is None:
                continue
            try:
                method(target)
                time.sleep(0.7)
                if self._dialog_type_is_active(target):
                    return True
            except Exception:
                continue
        expand = getattr(combo, "expand", None)
        if expand is not None:
            try:
                expand()
                time.sleep(0.3)
            except Exception:
                pass
        return False

    def _try_select_dialog_type_via_keyboard(self, target: str) -> None:
        normalized = self._normalize_dialog_type(target)
        if normalized == "запрос1с":
            keyboard.send_keys("{DOWN}{ENTER}", pause=0.05)
            return
        keyboard.send_keys("{HOME}{ENTER}", pause=0.05)

    def _dialog_type_is_active(self, target: str) -> bool:
        normalized = self._normalize_dialog_type(target)
        try:
            current = self._normalize_dialog_type(self._safe_text(self._locate_dialog_type_combo()))
            if current == normalized and current:
                return True
        except Exception:
            pass
        if normalized == "запрос1с":
            text_dump = self._window_dump_text(self.main_window)
            if "Открыть форму запроса 1С" in text_dump:
                return True
            if "Диалог ИИ" in text_dump and "Запрос 1С" in text_dump:
                return True
        return False

    def _enter_prompt(self) -> None:
        self.logger.info("Вводим пользовательское сообщение.")
        edit = self._locate_prompt_input()
        self._set_text_to_input(edit, self.config.prompt)
        current_value = self._read_input_value(edit)
        if current_value:
            self.logger.info(f"Поле ввода содержит: {current_value[:120]!r}")
        time.sleep(1)
        full_text = self._window_dump_text(self.main_window)
        if self.config.prompt.lower() not in full_text.lower():
            self.logger.info("Текст не отразился в общем dump окна, продолжаем по кнопке отправки.")

    def _send_prompt(self) -> None:
        self.logger.info("Нажимаем 'Отправить'.")
        button = self._locate_send_button()
        if self._click_send_button_until_started(button):
            self._handle_pending_approval()
            return
        self._capture_debug_artifacts("send_failure")
        raise RuntimeError("Кнопка 'Отправить' не запустила обработку запроса.")

    def _locate_send_button(self):
        try:
            return self._find_descendant_by_titles(["Отправить", "Send"], ["Button"], 8)
        except RuntimeError:
            pass
        candidates = []
        for item in self._iter_descendants(self.main_window):
            if self._safe_control_type(item) != "Button":
                continue
            try:
                rect = item.rectangle()
            except Exception:
                continue
            if rect.left >= 1250 and 120 <= rect.top <= 210 and rect.width() >= 120 and rect.height() >= 25:
                candidates.append(item)
        if not candidates:
            raise RuntimeError("Не найден элемент ['Отправить', 'Send'] (Button).")
        candidates.sort(key=lambda item: (abs(item.rectangle().top - 160), -item.rectangle().width()))
        self.logger.info("Кнопка 'Отправить' найдена по позиции на форме.")
        return candidates[0]

    def _click_send_button_until_started(self, button) -> bool:
        if self.config.mouse_control:
            try:
                self.logger.info("Mouse-control: нажимаем 'Отправить' мышью по экрану.")
                self._activate_main_window()
                self._click(button)
                time.sleep(2)
                self._handle_pending_approval()
                if self._submission_started():
                    self.logger.info("Отправка: форма начала обработку после mouse-control click.")
                    return True
            except Exception as exc:
                self.logger.info(f"Mouse-control отправка не сработала: {exc}")
        attempts = [
            ("click_input", lambda: button.click_input()),
            ("mouse.click", lambda: self._click(button)),
            ("keyboard ENTER", lambda: keyboard.send_keys("{ENTER}", pause=0.05)),
        ]
        for method_name, action in attempts:
            try:
                self.logger.info(f"Отправка: попытка через {method_name}.")
                self._activate_main_window()
                action()
                time.sleep(2)
                self._handle_pending_approval()
                if self._submission_started():
                    self.logger.info(f"Отправка: форма начала обработку после {method_name}.")
                    return True
            except Exception as exc:
                self.logger.info(f"Отправка через {method_name} не сработала: {exc}")
        return False

    def _submission_started(self) -> bool:
        text_dump = self._window_dump_text(self.main_window).lower()
        started_markers = (
            "выполняется",
            "ожидание",
            "готовится",
            "обработка",
            "остановить",
            "отправка сообщения",
        )
        if any(marker in text_dump for marker in started_markers):
            return True
        try:
            edit = self._locate_prompt_input()
            value = self._read_input_value(edit).strip()
            if not value:
                return True
        except Exception:
            pass
        return False

    def _wait_expected_response(self, baseline_success_count: int = 0) -> None:
        self.logger.info("Ждём ожидаемый ответ агента.")
        if self.config.expected_text == "__SUBMISSION_STARTED__":
            self.logger.info("Smoke-режим: достаточно подтверждения, что отправка стартовала.")
            return
        deadline = time.time() + self.config.timeout_sec
        expected = self.config.expected_text.lower()
        error_markers = (
            "задача завершена с ошибкой",
            "ошибка api",
            "ошибка:",
            "превышен лимит токенов",
            "остановлено:",
        )
        saw_running = False
        while time.time() < deadline:
            self._raise_if_error_dialog()
            self._handle_pending_approval()
            text_dump = self._window_dump_text(self.main_window).lower()
            if "остановить" in text_dump:
                saw_running = True
            if self._is_successfully_completed(text_dump):
                if self._success_marker_count(text_dump) <= baseline_success_count:
                    time.sleep(2)
                    continue
                if expected and expected not in text_dump:
                    self.logger.info("Форма показывает успешное завершение, ожидаемый текст недоступен в dump UI.")
                return
            for marker in error_markers:
                if marker in text_dump:
                    raise RuntimeError(f"В форме агента зафиксирована ошибка:\n{text_dump}")
            if saw_running and "отправить" in text_dump and "остановить" not in text_dump:
                self.logger.info("Кнопка вернулась в 'Отправить' после выполнения, считаем сессию агента завершённой.")
                return
            time.sleep(2)
        raise RuntimeError(f"Не дождались ожидаемого текста ответа: {self.config.expected_text!r}")

    def _signal_recording_start(self) -> None:
        if not self.config.record_start_marker:
            return
        marker_path = Path(self.config.record_start_marker)
        try:
            marker_path.parent.mkdir(parents=True, exist_ok=True)
            marker_path.write_text(str(time.time()), encoding="utf-8")
            self.logger.info(f"Сигнал старта записи: {marker_path}")
            time.sleep(1)
        except Exception as exc:
            self.logger.info(f"Не удалось записать marker старта записи: {exc}")

    def _run_query1c_form_scenario(self) -> None:
        self.logger.info("Запускаем UI-сценарий формы 'Запрос 1С'.")
        self._wait_window_text_contains("Открыть форму запроса 1С", 30)
        link = self._find_descendant_by_titles(
            ["Открыть форму запроса 1С"],
            ["Hyperlink", "Text", "Button"],
            20,
        )
        self._click(link)
        query_window = self._wait_for_process_window(["Запрос 1С", "Запрос1С"], 20)
        self.logger.info(f"Открыта форма запроса: {query_window.window_text()!r}")

        query_edit = self._locate_query_form_edit(query_window, 0)
        self._set_text_to_input_in_window(query_window, query_edit, self.config.query_text)
        self._wait_window_dump_contains(
            query_window,
            "Агент будет использовать эту версию",
            20,
        )

        execute_button = self._find_descendant_by_titles_in_window(
            query_window,
            ["Выполнить", "Execute"],
            ["Button"],
            20,
        )
        self._click(execute_button)
        self._wait_window_dump_contains(query_window, "Запрос выполнен.", self.config.timeout_sec)
        self._wait_window_dump_contains(query_window, self.config.expected_text, self.config.timeout_sec)

    def _show_query_form_preview(self) -> None:
        self.logger.info("Открываем форму 'Запрос 1С' для демонстрации текста запроса и результата.")
        self._activate_main_window()
        self._wait_window_text_contains("Открыть форму запроса 1С", 30)
        link = self._find_descendant_by_titles(
            ["Открыть форму запроса 1С"],
            ["Hyperlink", "Text", "Button"],
            20,
        )
        self._click(link)
        time.sleep(1)
        current_dump = self._window_dump_text(self.main_window)
        if "Запрос 1С" in current_dump and "Результат" in current_dump:
            query_window = self.main_window
        else:
            query_window = self._wait_for_process_window(["Запрос 1С", "Запрос1С"], 20)
        query_window.set_focus()
        time.sleep(4)
        dump = self._window_dump_text(query_window)
        if "Результат" not in dump:
            self.logger.info("Форма запроса открыта, но в dump не найден блок результата; продолжаем демонстрацию.")
        self._close_query_preview_window(query_window)
        self._activate_main_window()

    def _close_query_preview_window(self, query_window) -> None:
        try:
            close_button = self._find_descendant_by_titles_in_window(
                query_window,
                ["Закрыть"],
                ["Button"],
                5,
            )
            self._click(close_button)
            time.sleep(1)
            return
        except Exception as exc:
            self.logger.info(f"Не удалось закрыть форму кнопкой 'Закрыть': {exc}")
        if query_window == self.main_window:
            raise RuntimeError("Не удалось закрыть встроенную форму 'Запрос 1С' кнопкой 'Закрыть'.")
        try:
            query_window.close()
            time.sleep(1)
        except Exception as exc:
            self.logger.info(f"Не удалось закрыть форму через window.close(): {exc}")

    def _prepare_query1c_dialog_via_com(self) -> None:
        connection_string = _com_connection_string(self.config.base_path, self.config.user, self.config.password)
        self.logger.info("Подготавливаем диалог 'Запрос 1С' через COM до открытия UI.")
        self.com_connection = connect_to_1c(connection_string)
        if not self.com_connection:
            raise RuntimeError("Не удалось установить COM-подключение к 1С для подготовки диалога Запрос1С.")
        dialog_type = get_enum_value(self.com_connection, "ИИА_ТипДиалога", "Запрос1С")
        if dialog_type is None:
            raise RuntimeError("Не найдено перечисление ИИА_ТипДиалога.Запрос1С.")
        self.prepared_dialog_ref = call_procedure(
            self.com_connection,
            "ИИА_Сервер",
            "СоздатьНовыйДиалог",
            self.config.user,
            dialog_type,
        )
        if self.prepared_dialog_ref is None:
            raise RuntimeError("COM не вернул ссылку на подготовленный диалог Запрос1С.")
        call_procedure(
            self.com_connection,
            "ИИА_Сервер",
            "СохранитьЧерновикЗапроса1С",
            self.prepared_dialog_ref,
            self.config.query_text,
            "",
        )
        self.logger.info("Диалог 'Запрос 1С' подготовлен и сохранён как последний диалог пользователя.")

    def _wait_for_process_window(self, title_variants: list[str], timeout: int):
        deadline = time.time() + timeout
        wanted = [title.lower() for title in title_variants]
        while time.time() < deadline:
            self._raise_if_error_dialog()
            for win in Desktop(backend=self.config.backend).windows():
                try:
                    if self.process is not None and win.process_id() != self.process.pid:
                        continue
                    if not self._safe_is_visible(win):
                        continue
                    title = self._safe_text(win).lower()
                    if any(needle in title for needle in wanted):
                        return win
                except Exception:
                    continue
            time.sleep(1)
        raise RuntimeError(f"Не удалось дождаться окна: {title_variants!r}")

    def _locate_query_form_edit(self, window, index: int):
        candidates = []
        for item in self._iter_descendants(window):
            if self._safe_control_type(item) != "Edit":
                continue
            rect = item.rectangle()
            if rect.width() < 250 or rect.height() < 40:
                continue
            candidates.append(item)
        if not candidates:
            raise RuntimeError("Не найдены поля формы 'Запрос 1С'.")
        candidates.sort(key=lambda item: (item.rectangle().top, item.rectangle().left))
        if index >= len(candidates):
            raise RuntimeError(f"В форме 'Запрос 1С' найдено только {len(candidates)} полей Edit.")
        return candidates[index]

    def _set_text_to_input_in_window(self, window, control, text: str) -> None:
        self._activate_window(window)
        self._click(control)
        if self._set_text_via_uia(control, text, "поля окна запроса"):
            return
        hwnd = self._get_hwnd(control)
        if hwnd:
            self.logger.info(f"Пробуем native hwnd для поля окна запроса: {hwnd}")
            if self._set_text_via_hwnd(hwnd, text):
                time.sleep(0.5)
                if self._read_input_value(control):
                    return
        if self._set_text_via_rpa_in_window(window, control, text):
            return
        raise RuntimeError("Не удалось ввести текст в поле формы 'Запрос 1С'.")

    def _set_text_via_rpa_in_window(self, window, control, text: str) -> bool:
        rect = control.rectangle()
        coords = (rect.left + max(20, rect.width() // 4), rect.top + max(18, rect.height() // 2))
        try:
            self._activate_window(window)
            self._click_at(coords)
            time.sleep(0.2)
            keyboard.send_keys("^a", pause=0.05)
            keyboard.send_keys("{BACKSPACE}", pause=0.05)
            self._paste_text_to_active_window(text)
            time.sleep(0.4)
            keyboard.send_keys("{TAB}", pause=0.05)
            time.sleep(0.4)
            if self._read_input_value(control):
                return True
            if text.lower() in self._window_dump_text(window).lower():
                return True
        except Exception as exc:
            self.logger.info(f"RPA-ввод в окне запроса завершился ошибкой: {exc}")
        return False

    def _activate_window(self, window) -> None:
        try:
            window.set_focus()
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetForegroundWindow(window.handle)
        except Exception:
            pass
        time.sleep(0.2)

    def _find_descendant_by_titles_in_window(self, window, titles: list[str], control_types: list[str], timeout: int):
        deadline = time.time() + timeout
        wanted = {title.lower() for title in titles}
        allowed_types = set(control_types)
        while time.time() < deadline:
            self._raise_if_error_dialog()
            for item in self._iter_descendants(window):
                text = self._safe_text(item).lower()
                ctype = self._safe_control_type(item)
                if text in wanted and ctype in allowed_types:
                    return item
            time.sleep(1)
        raise RuntimeError(f"Не найден элемент {titles!r} ({', '.join(control_types)}) в окне.")

    def _wait_window_dump_contains(self, window, text: str, timeout: int) -> None:
        deadline = time.time() + timeout
        needle = text.lower()
        while time.time() < deadline:
            self._raise_if_error_dialog()
            if needle in self._window_dump_text(window).lower():
                return
            time.sleep(1)
        raise RuntimeError(f"Не найден текст в окне {self._safe_text(window)!r}: {text!r}")

    def _handle_pending_approval(self) -> None:
        full_text = self._window_dump_text(self.main_window).lower()
        approval_markers = (
            "требуется подтверждение",
            "pending approval",
            "риск:",
        )
        if not any(marker in full_text for marker in approval_markers):
            return
        self.approval_seen = True
        self.logger.info("Обнаружен pending approval, подтверждаем выполнение.")
        actions_map = {
            "approve": [
                ["Подтвердить", "Approve"],
            ],
            "without_confirmation": [
                ["Выполнять без подтверждения", "Execute without confirmation"],
            ],
            "auto": [
                ["Подтвердить", "Approve"],
                ["Выполнять без подтверждения", "Execute without confirmation"],
            ],
        }
        for titles in actions_map.get(self.config.approval_action, actions_map["auto"]):
            try:
                button = self._find_descendant_by_titles(titles, ["Button"], 5)
                self._click(button)
                time.sleep(1)
                return
            except Exception:
                continue

    def _is_successfully_completed(self, text_dump: str) -> bool:
        send_ready = "отправить" in text_dump and "остановить" not in text_dump
        if not send_ready:
            return False
        success_markers = (
            "задача выполнена успешно",
            "резюме выполненной работы",
            "задача завершена",
            "подтверждено по системным результатам",
            "открыть таблицу результатов",
            "успешно",
        )
        return any(marker in text_dump for marker in success_markers)

    def _success_marker_count(self, text_dump: str | None = None) -> int:
        if text_dump is None:
            text_dump = self._window_dump_text(self.main_window).lower()
        markers = (
            "задача выполнена успешно",
            "задача завершена",
            "подтверждено по системным результатам",
        )
        return sum(text_dump.count(marker) for marker in markers)

    def _find_descendant_by_titles(self, titles: list[str], control_types: list[str], timeout: int):
        deadline = time.time() + timeout
        wanted = {title.lower() for title in titles}
        allowed_types = set(control_types)
        while time.time() < deadline:
            self._raise_if_error_dialog()
            for item in self._iter_descendants():
                text = self._safe_text(item).lower()
                ctype = self._safe_control_type(item)
                if text in wanted and ctype in allowed_types:
                    return item
            time.sleep(1)
        raise RuntimeError(f"Не найден элемент {titles!r} ({', '.join(control_types)}).")

    def _open_agent_section(self, nav_item) -> None:
        rect = nav_item.rectangle()
        y = rect.top + max(1, rect.height() // 2)
        x_points = [
            rect.left + max(1, rect.width() // 2),
            rect.left + 50,
            rect.right - 50,
        ]
        for x in x_points:
            self.main_window.set_focus()
            mouse.click(coords=(x, y))
            time.sleep(2)
            try:
                if self._window_contains_any(["Диалоги", "Настройки пользователей", "Текущий диалог"]):
                    return
                self._find_descendant_by_titles(
                    ["ИИ Агент", "Диалоги", "Настройки пользователей"],
                    ["MenuItem", "Hyperlink", "Text", "ListItem"],
                    2,
                )
                return
            except Exception:
                continue
        raise RuntimeError("Не удалось раскрыть раздел 'ИИ Агент'.")

    def _wait_until_client_ready(self, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._raise_if_error_dialog()
            text_dump = self._window_dump_text(self.main_window)
            if "Выполняется расчет..." not in text_dump:
                return
            time.sleep(2)
        self.logger.info("Стартовая страница всё ещё занята, продолжаем попытку навигации.")

    def _find_descendant_exact(self, title: str, control_type: str, timeout: int):
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._raise_if_error_dialog()
            for item in self._iter_descendants():
                if self._safe_text(item) == title and self._safe_control_type(item) == control_type:
                    return item
            time.sleep(1)
        raise RuntimeError(f"Не найден элемент '{title}' ({control_type}).")

    def _wait_window_text_contains(self, text: str, timeout: int) -> None:
        deadline = time.time() + timeout
        needle = text.lower()
        while time.time() < deadline:
            self._raise_if_error_dialog()
            full_text = self._window_dump_text(self.main_window).lower()
            if needle in full_text:
                return
            time.sleep(1)
        raise RuntimeError(f"Не найден текст в окне: {text!r}")

    def _wait_agent_form_ready(self, timeout: int) -> None:
        deadline = time.time() + timeout
        while time.time() < deadline:
            self._raise_if_error_dialog()
            if self._window_contains_any(["Текущий диалог", "Новый диалог", "Отправить"]):
                return
            time.sleep(1)
        raise RuntimeError("Не удалось дождаться загрузки формы агента.")

    def _window_contains_any(self, texts: list[str]) -> bool:
        full_text = self._window_dump_text(self.main_window).lower()
        return any(text.lower() in full_text for text in texts)

    def _locate_prompt_input(self):
        candidates = []
        for item in self._iter_descendants():
            ctype = self._safe_control_type(item)
            if ctype != "Edit":
                continue
            text = self._safe_text(item).strip().lower()
            rect = item.rectangle()
            if rect.width() < 300 or rect.height() < 40:
                continue
            if rect.left < 240 or rect.top < 90:
                continue
            if "search" in text or "текущий диалог" in text or "decision timeline" in text:
                continue
            candidates.append(item)
        if not candidates:
            raise RuntimeError("Не найдено поле ввода сообщения в форме агента.")
        prompt_row_candidates = [item for item in candidates if 90 <= item.rectangle().top <= 230]
        if prompt_row_candidates:
            prompt_row_candidates.sort(
                key=lambda item: (
                    abs(item.rectangle().top - 110),
                    -item.rectangle().width(),
                    abs(item.rectangle().left - 270),
                )
            )
            return prompt_row_candidates[0]
        candidates.sort(
            key=lambda item: (
                abs(item.rectangle().top - 110),
                -item.rectangle().width(),
                abs(item.rectangle().left - 270),
            )
        )
        return candidates[0]

    def _set_text_to_input(self, control, text: str) -> None:
        self._activate_main_window()
        if self.config.mouse_control and self._set_text_via_mouse(control, text):
            return
        self._click(control)
        if self._set_text_via_physical_clipboard(control, text):
            return
        if self._set_text_via_ascii_keyboard(control, text):
            return
        if self._set_text_via_uia(control, text, "поля ввода"):
            return
        hwnd = self._get_hwnd(control)
        if hwnd and self.main_window is not None and hwnd != self.main_window.handle:
            self.logger.info(f"Пробуем native hwnd для поля ввода: {hwnd}")
            if self._set_text_via_hwnd(hwnd, text) and self._read_input_value(control):
                return
        elif hwnd:
            self.logger.info("Пропускаем native hwnd: 1C вернула HWND главного окна для поля ввода.")
        if self._set_text_via_rpa(control, text):
            return
        self._capture_debug_artifacts("input_failure")
        raise RuntimeError("Не удалось ввести текст в поле формы агента.")

    def _set_text_via_mouse(self, control, text: str) -> bool:
        if not text:
            return False
        point = None
        try:
            self.logger.info("Mouse-control: вводим текст кликом по экрану и посимвольным набором.")
            rect = control.rectangle()
            point = (
                rect.left + min(max(40, rect.width() // 4), max(40, rect.width() - 20)),
                rect.top + max(18, min(rect.height() // 2, rect.height() - 8)),
            )
            self._activate_main_window()
            self._click_at(point)
            keyboard.send_keys("^a", pause=0.05)
            keyboard.send_keys("{BACKSPACE}", pause=0.05)
            self._type_text_unicode_chars(text, delay_sec=0.035)
            time.sleep(0.3)
            value = self._read_input_value(control)
            if self._text_input_matches(value, text):
                return True
            if value:
                self.logger.info(f"Mouse-control: после посимвольного ввода поле содержит не весь текст: {value!r}.")
            full_text = self._window_dump_text(self.main_window).lower() if self.main_window else ""
            if text.lower() in full_text:
                return True
        except Exception as exc:
            self.logger.info(f"Mouse-control ввод не сработал: {exc}")
        try:
            self.logger.info("Mouse-control: пробуем посимвольный ввод физическими клавишами в RU-раскладке.")
            self._activate_main_window()
            if point is not None:
                self._click_at(point)
            else:
                self._click(control)
            keyboard.send_keys("^a", pause=0.05)
            keyboard.send_keys("{BACKSPACE}", pause=0.05)
            self._activate_keyboard_layout("00000419", control)
            self._type_text_physical_keyboard(text, delay_sec=0.045)
            time.sleep(0.4)
            value = self._read_input_value(control)
            if self._text_input_matches(value, text):
                return True
            if value:
                self.logger.info(f"Mouse-control: после физического ввода поле содержит не весь текст: {value!r}.")
            full_text = self._window_dump_text(self.main_window).lower() if self.main_window else ""
            if text.lower() in full_text:
                return True
        except Exception as exc:
            self.logger.info(f"Mouse-control физический посимвольный ввод не сработал: {exc}")
        try:
            self.logger.info("Mouse-control: посимвольный ввод не подтвердился, fallback на clipboard без Tab.")
            self._activate_main_window()
            if point is not None:
                self._click_at(point)
            else:
                self._click(control)
            keyboard.send_keys("^a", pause=0.05)
            keyboard.send_keys("{BACKSPACE}", pause=0.05)
            self._paste_text_to_active_window(text, send_unicode_fallback=False)
            time.sleep(0.3)
            value = self._read_input_value(control)
            return self._text_input_matches(value, text) or bool(value)
        except Exception as exc:
            self.logger.info(f"Mouse-control clipboard fallback не сработал: {exc}")
            return False

    def _text_input_matches(self, actual: str, expected: str) -> bool:
        actual_norm = (actual or "").strip().lower()
        expected_norm = (expected or "").strip().lower()
        return bool(expected_norm) and actual_norm == expected_norm

    def _activate_keyboard_layout(self, layout_id: str, control=None) -> None:
        if os.name != "nt":
            return
        user32 = ctypes.windll.user32
        user32.GetWindowThreadProcessId.argtypes = (ctypes.c_void_p, ctypes.c_void_p)
        user32.GetWindowThreadProcessId.restype = ctypes.c_ulong
        user32.GetKeyboardLayout.argtypes = (ctypes.c_ulong,)
        user32.GetKeyboardLayout.restype = ctypes.c_void_p
        hkl = user32.LoadKeyboardLayoutW(layout_id, 1)
        if not hkl:
            raise RuntimeError(f"Не удалось загрузить раскладку {layout_id}.")
        user32.ActivateKeyboardLayout(hkl, 0)
        target_lang = int(layout_id[-4:], 16)
        hwnds = []
        control_hwnd = self._get_hwnd(control) if control is not None else 0
        main_hwnd = getattr(self.main_window, "handle", 0) if self.main_window is not None else 0
        foreground_hwnd = user32.GetForegroundWindow()
        for hwnd in (control_hwnd, main_hwnd, foreground_hwnd):
            if hwnd and hwnd not in hwnds:
                hwnds.append(hwnd)
        WM_INPUTLANGCHANGEREQUEST = 0x0050
        for hwnd in hwnds:
            user32.PostMessageW(hwnd, WM_INPUTLANGCHANGEREQUEST, 0, hkl)
        time.sleep(0.2)
        if self._foreground_keyboard_lang_id() == target_lang:
            return
        for sequence in ("%{VK_SHIFT}", "^{VK_SHIFT}"):
            for _attempt in range(3):
                keyboard.send_keys(sequence, pause=0.08)
                time.sleep(0.2)
                if self._foreground_keyboard_lang_id() == target_lang:
                    return
        current_lang = self._foreground_keyboard_lang_id()
        raise RuntimeError(f"Не удалось переключить раскладку на {layout_id}; текущая={current_lang:04x}.")

    def _foreground_keyboard_lang_id(self) -> int:
        if os.name != "nt":
            return 0
        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return 0
        thread_id = user32.GetWindowThreadProcessId(hwnd, None)
        hkl = user32.GetKeyboardLayout(thread_id)
        return int(hkl) & 0xFFFF

    def _type_text_physical_keyboard(self, text: str, delay_sec: float = 0.04) -> None:
        ru_keys = {
            "й": 0x51,
            "ц": 0x57,
            "у": 0x45,
            "к": 0x52,
            "е": 0x54,
            "н": 0x59,
            "г": 0x55,
            "ш": 0x49,
            "щ": 0x4F,
            "з": 0x50,
            "х": 0xDB,
            "ъ": 0xDD,
            "ф": 0x41,
            "ы": 0x53,
            "в": 0x44,
            "а": 0x46,
            "п": 0x47,
            "р": 0x48,
            "о": 0x4A,
            "л": 0x4B,
            "д": 0x4C,
            "ж": 0xBA,
            "э": 0xDE,
            "я": 0x5A,
            "ч": 0x58,
            "с": 0x43,
            "м": 0x56,
            "и": 0x42,
            "т": 0x4E,
            "ь": 0x4D,
            "б": 0xBC,
            "ю": 0xBE,
            "ё": 0xC0,
        }
        for char in text:
            if char == " ":
                self._press_virtual_key(0x20)
            elif char.lower() in ru_keys:
                self._press_virtual_key(ru_keys[char.lower()], shift=char.isupper())
            elif char.isascii():
                vk = ord(char.upper())
                if 0x30 <= vk <= 0x5A:
                    self._press_virtual_key(vk, shift=char.isupper())
                else:
                    keyboard.send_keys(char, pause=0, with_spaces=True)
            else:
                raise RuntimeError(f"Нет физической клавиши для символа {char!r}.")
            if delay_sec > 0:
                time.sleep(delay_sec)

    def _press_virtual_key(self, vk_code: int, shift: bool = False) -> None:
        if os.name != "nt":
            raise RuntimeError("Virtual-key ввод доступен только на Windows.")
        user32 = ctypes.windll.user32
        KEYEVENTF_KEYUP = 0x0002
        VK_SHIFT = 0x10
        if shift:
            user32.keybd_event(VK_SHIFT, 0, 0, 0)
            time.sleep(0.01)
        user32.keybd_event(vk_code, 0, 0, 0)
        time.sleep(0.01)
        user32.keybd_event(vk_code, 0, KEYEVENTF_KEYUP, 0)
        if shift:
            time.sleep(0.01)
            user32.keybd_event(VK_SHIFT, 0, KEYEVENTF_KEYUP, 0)

    def _type_text_unicode_chars(self, text: str, delay_sec: float = 0.03) -> None:
        if os.name != "nt":
            keyboard.send_keys(text, pause=delay_sec, with_spaces=True)
            return

        user32 = ctypes.windll.user32
        user32.SendInput.argtypes = (ctypes.c_uint, ctypes.c_void_p, ctypes.c_int)
        user32.SendInput.restype = ctypes.c_uint
        KEYEVENTF_KEYUP = 0x0002
        KEYEVENTF_UNICODE = 0x0004
        ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong

        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint),
                ("time", ctypes.c_uint),
                ("dwExtraInfo", ULONG_PTR),
            ]

        class INPUTUNION(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint), ("union", INPUTUNION)]

        def send_code_unit(code_unit: int) -> None:
            down = INPUT(
                type=1,
                union=INPUTUNION(
                    ki=KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE, 0, 0)
                ),
            )
            up = INPUT(
                type=1,
                union=INPUTUNION(
                    ki=KEYBDINPUT(0, code_unit, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0)
                ),
            )
            sent_down = user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
            sent_up = user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
            if sent_down != 1 or sent_up != 1:
                raise RuntimeError(f"SendInput не отправил unicode code unit {code_unit}.")

        for char in text:
            encoded = char.encode("utf-16-le")
            for index in range(0, len(encoded), 2):
                send_code_unit(encoded[index] | (encoded[index + 1] << 8))
            if delay_sec > 0:
                time.sleep(delay_sec)

    def _set_text_via_physical_clipboard(self, control, text: str) -> bool:
        if not text:
            return False
        try:
            self.logger.info("Пробуем физический ввод через clipboard paste.")
            self._activate_main_window()
            try:
                control.set_focus()
            except Exception:
                pass
            try:
                control.click_input()
            except Exception:
                self._click(control)
            time.sleep(0.4)
            keyboard.send_keys("^a", pause=0.05)
            keyboard.send_keys("{BACKSPACE}", pause=0.05)
            self._paste_text_to_active_window(text, send_unicode_fallback=False)
            time.sleep(0.4)
            keyboard.send_keys("{TAB}", pause=0.05)
            time.sleep(0.7)
            value = self._read_input_value(control)
            if value:
                self.logger.info("Физический clipboard-ввод: поле вернуло непустое значение.")
                return True
        except Exception as exc:
            self.logger.info(f"Физический clipboard-ввод не сработал: {exc}")
        return False

    def _set_text_via_ascii_keyboard(self, control, text: str) -> bool:
        if not text or not text.isascii():
            return False
        try:
            self.logger.info("Пробуем физический ASCII-ввод клавиатурой.")
            self._activate_main_window()
            try:
                control.set_focus()
            except Exception:
                pass
            try:
                control.click_input()
            except Exception:
                self._click(control)
            time.sleep(0.4)
            keyboard.send_keys("^a", pause=0.05)
            keyboard.send_keys("{BACKSPACE}", pause=0.05)
            keyboard.send_keys(text, pause=0.02, with_spaces=True)
            time.sleep(0.4)
            keyboard.send_keys("{TAB}", pause=0.05)
            time.sleep(0.6)
            value = self._read_input_value(control)
            if value:
                self.logger.info("Физический ASCII-ввод: поле вернуло непустое значение.")
                return True
        except Exception as exc:
            self.logger.info(f"Физический ASCII-ввод не сработал: {exc}")
        return False

    def _read_input_value(self, control) -> str:
        try:
            iface_value = getattr(control, "iface_value", None)
            if iface_value is not None:
                value = iface_value.CurrentValue
                if value is not None:
                    return str(value).strip()
        except Exception:
            pass
        return self._safe_text(control)

    def _set_text_via_uia(self, control, text: str, label: str) -> bool:
        attempts = [
            ("ValuePattern.SetValue", lambda: control.iface_value.SetValue(text)),
            ("set_edit_text", lambda: control.set_edit_text(text)),
            ("set_text", lambda: control.set_text(text)),
        ]
        for method_name, setter in attempts:
            try:
                self.logger.info(f"Пробуем UIA-ввод через {method_name} для {label}.")
                setter()
                time.sleep(0.5)
                value = self._read_input_value(control)
                if value:
                    self.logger.info(f"UIA-ввод через {method_name}: поле вернуло непустое значение.")
                    if self._commit_uia_text_with_keyboard(control, text):
                        return True
                    self.logger.info(f"UIA-ввод через {method_name}: значение есть, но клавиатурный commit не подтвердился.")
                full_text = self._window_dump_text(self.main_window).lower() if self.main_window else ""
                if text.lower() in full_text:
                    self.logger.info(f"UIA-ввод через {method_name}: текст обнаружен в общем дампе окна.")
                    if self._commit_uia_text_with_keyboard(control, text):
                        return True
            except Exception as exc:
                self.logger.info(f"UIA-ввод через {method_name} не сработал: {exc}")
        return False

    def _commit_uia_text_with_keyboard(self, control, text: str) -> bool:
        commit_sequences = (
            "^a{BACKSPACE}",
            "{END}{SPACE}{BACKSPACE}{TAB}",
        )
        for index, sequence in enumerate(commit_sequences, start=1):
            try:
                self.logger.info(f"UIA-ввод: commit клавиатурой, попытка {index}.")
                self._activate_main_window()
                try:
                    control.set_focus()
                except Exception:
                    pass
                try:
                    control.click_input()
                except Exception:
                    self._click(control)
                time.sleep(0.3)
                if sequence == "^a{BACKSPACE}":
                    keyboard.send_keys("^a", pause=0.05)
                    keyboard.send_keys("{BACKSPACE}", pause=0.05)
                    self._paste_text_to_active_window(text, send_unicode_fallback=False)
                    time.sleep(0.4)
                    keyboard.send_keys("{TAB}", pause=0.05)
                else:
                    keyboard.send_keys(sequence, pause=0.05)
                time.sleep(0.6)
                value = self._read_input_value(control)
                if value:
                    return True
            except Exception as exc:
                self.logger.info(f"UIA-ввод: commit попытка {index} завершилась ошибкой: {exc}")
        return False

    def _get_hwnd(self, control) -> int:
        for attr in ("handle",):
            try:
                value = getattr(control, attr, None)
                if isinstance(value, int) and value:
                    return value
            except Exception:
                pass
        try:
            value = getattr(control.element_info, "handle", 0)
            if isinstance(value, int) and value:
                return value
        except Exception:
            pass
        try:
            rect = control.rectangle()
            class POINT(ctypes.Structure):
                _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]
            point = POINT(rect.left + max(1, rect.width() // 2), rect.top + max(1, rect.height() // 2))
            value = ctypes.windll.user32.WindowFromPoint(point)
            if isinstance(value, int) and value:
                return value
        except Exception:
            pass
        return 0

    def _set_text_via_hwnd(self, hwnd: int, text: str) -> bool:
        WM_SETTEXT = 0x000C
        EM_SETSEL = 0x00B1
        EM_REPLACESEL = 0x00C2
        WM_CHAR = 0x0102
        try:
            user32 = ctypes.windll.user32
            user32.SetForegroundWindow(self.main_window.handle)
            user32.SendMessageW(hwnd, EM_SETSEL, 0, -1)
            buffer = ctypes.create_unicode_buffer(text)
            result = user32.SendMessageW(hwnd, WM_SETTEXT, 0, ctypes.cast(buffer, ctypes.c_wchar_p))
            if result == 0:
                user32.SendMessageW(hwnd, EM_SETSEL, -1, -1)
                replace_buffer = ctypes.create_unicode_buffer(text)
                user32.SendMessageW(hwnd, EM_REPLACESEL, 1, ctypes.cast(replace_buffer, ctypes.c_wchar_p))
            if not self._safe_text_by_hwnd(hwnd):
                for ch in text:
                    user32.SendMessageW(hwnd, WM_CHAR, ord(ch), 0)
            user32.SendMessageW(hwnd, 0x000F, 0, 0)
            keyboard.send_keys("{TAB}", pause=0.05)
            return True
        except Exception:
            return False

    def _set_text_via_rpa(self, control, text: str) -> bool:
        rect = control.rectangle()
        anchor_points = [
            (rect.left + 18, rect.top + 18),
            (rect.left + max(30, rect.width() // 6), rect.top + max(18, rect.height() // 2)),
            (rect.left + max(40, rect.width() // 3), rect.top + max(18, rect.height() // 2)),
            (rect.left + max(50, rect.width() // 2), rect.top + max(18, rect.height() // 2)),
        ]
        for index, coords in enumerate(anchor_points, start=1):
            try:
                self.logger.info(f"RPA-ввод: попытка {index}, фокус в точку {coords}.")
                self._activate_main_window()
                self._click_at(coords)
                time.sleep(0.5)
                keyboard.send_keys("^a", pause=0.05)
                keyboard.send_keys("{BACKSPACE}", pause=0.05)
                self._paste_text_to_active_window(text, send_unicode_fallback=False)
                time.sleep(0.8)
                if self._read_input_value(control):
                    self.logger.info("RPA-ввод: поле вернуло непустое значение.")
                    return True
                full_text = self._window_dump_text(self.main_window).lower()
                if text.lower() in full_text:
                    self.logger.info("RPA-ввод: текст обнаружен в общем дампе окна.")
                    return True
                keyboard.send_keys("{TAB}", pause=0.05)
                time.sleep(0.4)
            except Exception as exc:
                self.logger.info(f"RPA-ввод: попытка {index} завершилась ошибкой: {exc}")
        return False

    def _activate_main_window(self) -> None:
        try:
            self.main_window.set_focus()
        except Exception:
            pass
        try:
            ctypes.windll.user32.SetForegroundWindow(self.main_window.handle)
        except Exception:
            pass
        time.sleep(0.2)

    def _click_at(self, coords: tuple[int, int]) -> None:
        mouse.click(coords=coords)
        time.sleep(0.2)

    def _double_click_at(self, coords: tuple[int, int]) -> None:
        mouse.double_click(coords=coords)
        time.sleep(0.2)

    def _drag_select_input_area(self, rect) -> None:
        y = rect.top + max(18, rect.height() // 2)
        start = (rect.left + max(20, rect.width() // 8), y)
        end = (rect.right - max(20, rect.width() // 8), y)
        self._mouse_drag(start, end)
        keyboard.send_keys("^a", pause=0.05)
        keyboard.send_keys("{BACKSPACE}", pause=0.05)

    def _mouse_drag(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        self._set_cursor_pos(*start)
        self._mouse_left_down()
        time.sleep(0.1)
        self._set_cursor_pos(*end)
        time.sleep(0.1)
        self._mouse_left_up()
        time.sleep(0.2)

    def _paste_text_to_active_window(self, text: str, send_unicode_fallback: bool = True) -> None:
        self._set_clipboard_text(text)
        keyboard.send_keys("^v", pause=0.05)
        time.sleep(0.1)
        if send_unicode_fallback:
            self._send_input_unicode_text(text)

    def _set_clipboard_text(self, text: str) -> None:
        GMEM_MOVEABLE = 0x0002
        CF_UNICODETEXT = 13
        kernel32 = ctypes.windll.kernel32
        user32 = ctypes.windll.user32
        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = ctypes.c_void_p
        kernel32.GlobalLock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalLock.restype = ctypes.c_void_p
        kernel32.GlobalUnlock.argtypes = [ctypes.c_void_p]
        kernel32.GlobalUnlock.restype = ctypes.c_int
        kernel32.GlobalFree.argtypes = [ctypes.c_void_p]
        kernel32.GlobalFree.restype = ctypes.c_void_p
        user32.OpenClipboard.argtypes = [ctypes.c_void_p]
        user32.OpenClipboard.restype = ctypes.c_int
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_int
        user32.SetClipboardData.argtypes = [ctypes.c_uint, ctypes.c_void_p]
        user32.SetClipboardData.restype = ctypes.c_void_p
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_int
        data = (text + "\x00").encode("utf-16le")
        handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        if not handle:
            raise RuntimeError("Не удалось выделить память под буфер обмена.")
        pointer = kernel32.GlobalLock(handle)
        if not pointer:
            kernel32.GlobalFree(handle)
            raise RuntimeError("Не удалось заблокировать память под буфер обмена.")
        ctypes.memmove(pointer, data, len(data))
        kernel32.GlobalUnlock(handle)
        if not user32.OpenClipboard(0):
            kernel32.GlobalFree(handle)
            raise RuntimeError("Не удалось открыть буфер обмена.")
        try:
            user32.EmptyClipboard()
            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                raise RuntimeError("Не удалось записать текст в буфер обмена.")
            handle = None
        finally:
            user32.CloseClipboard()
            if handle:
                kernel32.GlobalFree(handle)

    def _set_cursor_pos(self, x: int, y: int) -> None:
        ctypes.windll.user32.SetCursorPos(x, y)

    def _mouse_left_down(self) -> None:
        ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)

    def _mouse_left_up(self) -> None:
        ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    def _safe_text_by_hwnd(self, hwnd: int) -> str:
        try:
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            if length <= 0:
                return ""
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value.strip()
        except Exception:
            return ""

    def _send_input_unicode_text(self, text: str) -> None:
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_ulong),
                ("time", ctypes.c_ulong),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class _INPUTunion(ctypes.Union):
            _fields_ = [("ki", KEYBDINPUT)]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_ulong), ("union", _INPUTunion)]

        KEYEVENTF_UNICODE = 0x0004
        KEYEVENTF_KEYUP = 0x0002
        for ch in text:
            extra = ctypes.c_ulong(0)
            down = INPUT(1, _INPUTunion(ki=KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE, 0, ctypes.pointer(extra))))
            up = INPUT(1, _INPUTunion(ki=KEYBDINPUT(0, ord(ch), KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, ctypes.pointer(extra))))
            ctypes.windll.user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
            ctypes.windll.user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))

    def _raise_if_error_dialog(self) -> None:
        for win in Desktop(backend=self.config.backend).windows():
            try:
                if self.client_pids and win.process_id() not in self.client_pids:
                    continue
                if not self.client_pids and self.process is not None and win.process_id() != self.process.pid:
                    continue
                if not self._safe_is_visible(win):
                    continue
                text_dump = self._window_dump_text(win)
                text_dump_lower = text_dump.lower()
                error_markers = (
                    "сформировать отчет об ошибке",
                    "generate error report",
                    "lock conflict during the transaction",
                    "database object read integrity violation",
                    "не определена",
                )
                if any(marker in text_dump_lower for marker in error_markers):
                    self._try_close_error_dialog(win)
                    raise RuntimeError(f"1С показала модальную ошибку:\n{text_dump.strip()}")
            except RuntimeError:
                raise
            except Exception:
                continue

    def _try_close_error_dialog(self, window) -> None:
        for item in self._iter_descendants(window):
            if self._safe_text(item).upper() in ("OK", "ОК") and self._safe_control_type(item) == "Button":
                try:
                    self._click(item)
                except Exception:
                    pass
                return

    def _click(self, control) -> None:
        rect = control.rectangle()
        coords = (rect.left + max(1, rect.width() // 2), rect.top + max(1, rect.height() // 2))
        mouse.click(coords=coords)
        time.sleep(1)

    def _double_click(self, control) -> None:
        rect = control.rectangle()
        coords = (rect.left + max(1, rect.width() // 2), rect.top + max(1, rect.height() // 2))
        mouse.double_click(coords=coords)
        time.sleep(1.5)

    def _iter_descendants(self, window=None):
        if window is None:
            window = self.main_window
        if window is None:
            return []
        try:
            items = window.descendants()
        except Exception:
            return []
        result = []
        for item in items:
            try:
                _ = item.element_info.control_type
                result.append(item)
            except Exception:
                continue
        return result

    def _safe_text(self, control) -> str:
        try:
            return (control.window_text() or "").strip()
        except Exception:
            return ""

    def _safe_control_type(self, control) -> str:
        try:
            return control.element_info.control_type or ""
        except Exception:
            return ""

    def _safe_is_visible(self, control) -> bool:
        try:
            return bool(control.is_visible())
        except Exception:
            return False

    def _window_dump_text(self, window) -> str:
        chunks: list[str] = []
        for item in self._iter_descendants(window):
            text = self._safe_text(item)
            if text:
                chunks.append(text)
        return "\n".join(chunks)

    def _window_dump_controls(self, window) -> str:
        chunks: list[str] = []
        for item in self._iter_descendants(window):
            try:
                text = self._safe_text(item)
                ctype = self._safe_control_type(item)
                rect = item.rectangle()
                hwnd = self._get_hwnd(item)
                class_name = ""
                try:
                    if hwnd:
                        class_buf = ctypes.create_unicode_buffer(256)
                        ctypes.windll.user32.GetClassNameW(hwnd, class_buf, 255)
                        class_name = class_buf.value
                except Exception:
                    class_name = ""
                chunks.append(
                    f"text={text!r} | type={ctype!r} | hwnd={hwnd!r} | class={class_name!r} | rect=({rect.left},{rect.top},{rect.right},{rect.bottom})"
                )
            except Exception:
                continue
        return "\n".join(chunks)

    def _capture_debug_artifacts(self, prefix: str = "ui_failure") -> None:
        if not self.config.screenshot_dir or self.main_window is None:
            return
        target_dir = Path(self.config.screenshot_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        dump_path = target_dir / f"{prefix}_{stamp}.txt"
        controls_path = target_dir / f"{prefix}_controls_{stamp}.txt"
        try:
            image = self.main_window.capture_as_image()
            if image is not None:
                image_path = target_dir / f"{prefix}_{stamp}.png"
                image.save(image_path)
                self.logger.info(f"Сохранён скриншот: {image_path}")
            else:
                self.logger.info("capture_as_image() вернул None, png-скриншот пропущен.")
        except Exception as exc:
            self.logger.error(f"Не удалось сохранить скриншот: {exc}")
        try:
            dump_path.write_text(self._window_dump_text(self.main_window), encoding="utf-8")
            self.logger.info(f"Сохранён dump окна: {dump_path}")
        except Exception as exc:
            self.logger.error(f"Не удалось сохранить dump окна: {exc}")
        try:
            controls_path.write_text(self._window_dump_controls(self.main_window), encoding="utf-8")
            self.logger.info(f"Сохранён dump контролов окна: {controls_path}")
        except Exception as exc:
            self.logger.error(f"Не удалось сохранить dump контролов окна: {exc}")

    def _close_client(self) -> None:
        self.logger.info("Закрываем клиент 1С.")
        if not self.process:
            return
        try:
            if self.main_window is not None:
                self.main_window.close()
                time.sleep(2)
        except Exception:
            pass
        try:
            self.process.terminate()
            self.process.wait(timeout=15)
        except Exception:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"Stop-Process -Id {self.process.pid} -Force -ErrorAction SilentlyContinue",
                ],
                check=False,
                timeout=15,
            )

    @staticmethod
    def _clear_proxy_env(env: dict[str, str]) -> None:
        if env.get("AI_AGENT_KEEP_PROXY_ENV") == "1":
            return
        for name in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        ):
            env.pop(name, None)


def parse_args() -> UiConfig:
    parser = argparse.ArgumentParser(
        description="Desktop UI тест формы ИИ агента без Vanessa и без COM"
    )
    parser.add_argument(
        "--platform-exe",
        default=r"C:\Program Files\1cv8\8.5.1.1150\bin\1cv8.exe",
        help="Путь к 1cv8.exe",
    )
    parser.add_argument(
        "--base-path",
        default=DEFAULT_CONNECTION_STRING,
        help="Путь к файловой базе 1С или строка Srvr/Ref",
    )
    parser.add_argument(
        "--user",
        default="Администратор",
        help="Пользователь 1С",
    )
    parser.add_argument(
        "--password",
        default="",
        help="Пароль пользователя 1С",
    )
    parser.add_argument(
        "--prompt",
        default="какие поля есть у справочника Контрагенты",
        help="Текст сообщения агенту",
    )
    parser.add_argument(
        "--followups-json",
        default="[]",
        help="JSON-массив follow-up сообщений для отправки после первого ответа",
    )
    parser.add_argument(
        "--followups-file",
        default="",
        help="Файл с JSON-массивом follow-up сообщений",
    )
    parser.add_argument(
        "--show-query-between-turns",
        action="store_true",
        help="После каждого хода открывать форму Запрос 1С, показывать запрос/результат и закрывать её",
    )
    parser.add_argument(
        "--mouse-control",
        action="store_true",
        help="Выполнять основные действия мышью по экрану, как пользователь",
    )
    parser.add_argument(
        "--dialog-type",
        default="Агент",
        help="Тип диалога в форме агента",
    )
    parser.add_argument(
        "--expected-text",
        default="Поля успешно получены",
        help="Ожидаемый фрагмент ответа",
    )
    parser.add_argument(
        "--timeout-sec",
        type=int,
        default=180,
        help="Таймаут ожидания ответа",
    )
    parser.add_argument(
        "--startup-timeout-sec",
        type=int,
        default=90,
        help="Таймаут старта клиента",
    )
    parser.add_argument(
        "--backend",
        default="uia",
        choices=["uia", "win32"],
        help="Backend pywinauto",
    )
    parser.add_argument(
        "--log-file",
        default=str(Path("automation") / "logs" / "ui_pywinauto.log"),
        help="Файл лога",
    )
    parser.add_argument(
        "--screenshot-dir",
        default=str(Path("automation") / "logs" / "ui_artifacts"),
        help="Каталог для артефактов при падении",
    )
    parser.add_argument(
        "--leave-open",
        action="store_true",
        help="Не закрывать 1С после теста",
    )
    parser.add_argument(
        "--approval-action",
        default="auto",
        choices=["auto", "approve", "without_confirmation"],
        help="Как обрабатывать pending approval в UI тесте",
    )
    parser.add_argument(
        "--require-approval",
        action="store_true",
        help="Падать, если в UI не появилось ручное подтверждение",
    )
    parser.add_argument(
        "--test-case",
        default="standard",
        choices=["standard", "query1c_form", "web_query1c", "desktop_diag"],
        help="Какой UI-сценарий запускать",
    )
    parser.add_argument(
        "--query-text",
        default="ВЫБРАТЬ 2 КАК Новое",
        help="Текст запроса для сценария query1c_form",
    )
    parser.add_argument(
        "--query-params-json",
        default="",
        help="Параметры запроса в JSON для сценариев Query1C",
    )
    parser.add_argument(
        "--web-url",
        default=DEFAULT_WEB_URL,
        help="URL опубликованного web-client 1С",
    )
    parser.add_argument(
        "--chrome-exe",
        default=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        help="Путь к Chrome для browser UI test",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Запускать browser UI test с видимым окном браузера",
    )
    parser.add_argument(
        "--skip-com-prepare",
        action="store_true",
        help="Не подготавливать Query1C через COM внутри гостя",
    )
    parser.add_argument(
        "--record-start-marker",
        default="",
        help="Файл-marker: когда тест готов к пользовательским действиям, он создаёт файл для старта записи",
    )
    args = parser.parse_args()
    try:
        followups_source = args.followups_json
        if args.followups_file:
            followups_source = Path(args.followups_file).read_text(encoding="utf-8-sig")
        followups = json.loads(followups_source)
        if not isinstance(followups, list):
            followups = []
        followups = [str(item) for item in followups if str(item).strip()]
    except Exception:
        followups = []
    return UiConfig(
        platform_exe=args.platform_exe,
        base_path=args.base_path,
        user=args.user,
        password=args.password,
        prompt=args.prompt,
        followups=followups,
        show_query_between_turns=args.show_query_between_turns,
        mouse_control=args.mouse_control,
        dialog_type=args.dialog_type,
        expected_text=args.expected_text,
        timeout_sec=args.timeout_sec,
        startup_timeout_sec=args.startup_timeout_sec,
        backend=args.backend,
        log_file=args.log_file,
        screenshot_dir=args.screenshot_dir,
        leave_open=args.leave_open,
        approval_action=args.approval_action,
        require_approval=args.require_approval,
        test_case=args.test_case,
        query_text=args.query_text,
        query_params_json=args.query_params_json,
        web_url=args.web_url,
        chrome_exe=args.chrome_exe,
        headed=args.headed,
        skip_com_prepare=args.skip_com_prepare,
        record_start_marker=args.record_start_marker,
    )


def run_web_query1c_test(config: UiConfig, logger: Logger) -> int:
    web_script = REPO_ROOT / "automation" / "ui" / "web_query1c_test.py"
    web_url = config.web_url
    if isinstance(config.platform_exe, str) and config.platform_exe.lower().startswith(("http://", "https://")):
        web_url = config.platform_exe
    command = [
        sys.executable,
        "-u",
        str(web_script),
        "--web-url",
        web_url,
        "--chrome-exe",
        config.chrome_exe,
        "--base-path",
        config.base_path,
        "--user",
        config.user,
        "--password",
        config.password,
        "--query-text",
        config.query_text,
        "--query-params-json",
        config.query_params_json,
        "--expected-text",
        config.expected_text,
        "--timeout-sec",
        str(config.timeout_sec),
    ]
    if config.log_file:
        command.extend(["--log-file", config.log_file])
    if config.screenshot_dir:
        command.extend(["--artifact-dir", config.screenshot_dir])
    if config.headed:
        command.append("--headed")
    if config.skip_com_prepare or HOST_PREPARED_QUERY1C_MARKER in config.prompt:
        command.append("--skip-com-prepare")

    logger.info("Переключаемся на browser UI сценарий web_query1c.")
    process = subprocess.run(
        command,
        cwd=REPO_ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if process.stdout:
        print(process.stdout, end="")
    return process.returncode


def run_desktop_diagnostics(config: UiConfig, logger: Logger) -> int:
    candidates = [
        r"C:\Tools\1cv8\8.5.1.1150\bin\1cv8.exe",
        r"C:\Program Files\1cv8\8.5.1.1150\bin\1cv8.exe",
        r"C:\Program Files\1cv8\common\1cestart.exe",
        r"C:\Program Files (x86)\1cv8\common\1cestart.exe",
    ]
    found = [candidate for candidate in candidates if Path(candidate).exists()]
    logger.info(f"Desktop diagnostics, found executables: {found}")
    if not found:
        raise RuntimeError("На VM не найден ни один ожидаемый путь к 1С клиенту.")
    client_env = os.environ.copy()
    OneCAgentUiTest._clear_proxy_env(client_env)
    cmd = [
        config.platform_exe,
        "ENTERPRISE",
        "/DisableStartupDialogs",
        "/DisableStartupMessages",
        *_enterprise_connection_args(config.base_path),
        "/N",
        config.user,
    ]
    if config.password:
        cmd.extend(["/P", config.password])
    if config.log_file:
        cmd.extend(["/Out", str(Path(config.log_file).with_name("desktop_1c_startup.log").resolve()), "-NoTruncate"])
    logger.info(f"Desktop diagnostics, launch command: {cmd}")
    process = None
    try:
        process = subprocess.Popen(cmd, env=client_env, cwd=str(Path(config.platform_exe).parent))
        time.sleep(15)
        windows = []
        for win in Desktop(backend=config.backend).windows():
            try:
                if win.process_id() != process.pid:
                    continue
                windows.append(
                    {
                        "title": win.window_text(),
                        "visible": win.is_visible(),
                        "enabled": win.is_enabled(),
                        "class_name": win.class_name(),
                    }
                )
            except Exception:
                continue
        logger.info(f"Desktop diagnostics, process windows: {windows}")
    finally:
        if process is not None:
            try:
                process.terminate()
                process.wait(timeout=5)
            except Exception:
                try:
                    process.kill()
                except Exception:
                    pass
    return 0


def main() -> int:
    setup_console_encoding()
    config = parse_args()
    logger = Logger(config.log_file)
    if config.test_case == "web_query1c":
        return run_web_query1c_test(config, logger)
    if config.test_case == "desktop_diag":
        return run_desktop_diagnostics(config, logger)
    runner = OneCAgentUiTest(config, logger)
    return runner.run()


if __name__ == "__main__":
    raise SystemExit(main())
