# -*- coding: utf-8 -*-
"""
Браузерный UI тест опубликованного веб-клиента 1С для сценария Запрос1С.

Текущий сценарий:
1. Подготавливает диалог Запрос1С через COM, чтобы агент/форма получили актуальный черновик.
2. Открывает опубликованный web-client в Chrome через DevTools Protocol.
3. Выполняет вход под пользователем 1С.
4. Пытается открыть команду "ИИ Агент" через hash-навигацию web-клиента.
5. Проверяет, что форма агента открылась и содержит маркеры режима Запрос1С.

Если web-клиент упирается в отсутствие лицензии, тест падает с явной причиной,
чтобы это было видно в CI и в ручных прогонах.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    import websocket
    from websocket import WebSocketTimeoutException
except ModuleNotFoundError:
    subprocess.run(
        [sys.executable, "-m", "pip", "install", "websocket-client>=1.8.0"],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    import websocket
    from websocket import WebSocketTimeoutException

REPO_ROOT = Path(__file__).resolve().parents[2]
AUTOMATION_ROOT = REPO_ROOT / "automation"
for _path in (REPO_ROOT, AUTOMATION_ROOT):
    _path_str = str(_path)
    if _path_str not in sys.path:
        sys.path.insert(0, _path_str)

from com_1c import call_procedure, connect_to_1c, get_enum_value


DEFAULT_CONNECTION_STRING = 'Srvr="192.168.2.126:2541";Ref="fresh-unf";'
DEFAULT_WEB_URL = "http://192.168.2.127/fresh-unf"


def _parse_1c_connection_string(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, raw in re.findall(r"([A-Za-zА-Яа-я0-9_]+)\s*=\s*(\"(?:[^\"]|\"\")*\"|[^;]*)\s*;?", value or ""):
        item = raw.strip()
        if item.startswith('"') and item.endswith('"'):
            item = item[1:-1].replace('""', '"')
        result[key.lower()] = item
    return result


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


@dataclass
class WebUiConfig:
    web_url: str
    chrome_exe: str
    base_path: str
    user: str
    password: str
    query_text: str
    query_params_json: str
    expected_text: str
    timeout_sec: int
    log_file: Optional[str]
    artifact_dir: Optional[str]
    headless: bool
    skip_com_prepare: bool


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


class BrowserQuery1CTest:
    def __init__(self, config: WebUiConfig, logger: Logger) -> None:
        self.config = config
        self.logger = logger
        self.browser_process: Optional[subprocess.Popen[str]] = None
        self.user_data_dir: Optional[str] = None
        self.websocket = None
        self.session_id = ""
        self.message_id = 0
        self.debug_port = 0

    def run(self) -> int:
        try:
            self.logger.info(f"Старт browser Query1C test: web_url={self.config.web_url}")
            if not self.config.skip_com_prepare:
                self._prepare_query1c_dialog_via_com()
            self._launch_browser()
            self._open_initial_target()
            self._login()
            self._open_agent_command()
            self._assert_query1c_markers()
            self._open_query_form()
            self._assert_parameter_table()
            self._execute_query()
            self.logger.info("Браузерный UI тест Query1C завершён успешно.")
            return 0
        except Exception as exc:
            self.logger.error(str(exc))
            self._capture_artifacts()
            return 1
        finally:
            self._close()

    def _prepare_query1c_dialog_via_com(self) -> None:
        connection_string = _com_connection_string(self.config.base_path, self.config.user, self.config.password)
        self.logger.info("Подготавливаем диалог Запрос1С через COM.")
        connection = connect_to_1c(connection_string)
        if not connection:
            raise RuntimeError("Не удалось открыть COM-подключение к 1С.")
        dialog_type = get_enum_value(connection, "ИИА_ТипДиалога", "Запрос1С")
        if dialog_type is None:
            raise RuntimeError("Не найдено перечисление ИИА_ТипДиалога.Запрос1С.")
        dialog_ref = call_procedure(
            connection,
            "ИИА_Сервер",
            "СоздатьНовыйДиалог",
            self.config.user,
            dialog_type,
        )
        if dialog_ref is None:
            raise RuntimeError("COM не вернул ссылку на диалог Запрос1С.")
        call_procedure(
            connection,
            "ИИА_Сервер",
            "СохранитьЧерновикЗапроса1С",
            dialog_ref,
            self.config.query_text,
            self.config.query_params_json,
        )
        self.logger.info("Черновик Запрос1С подготовлен.")

    def _launch_browser(self) -> None:
        browser_exe = self._resolve_browser_exe()
        self.debug_port = self._pick_free_port()
        self.user_data_dir = tempfile.mkdtemp(prefix="browser-query1c-")
        args = [
            browser_exe,
            f"--remote-debugging-port={self.debug_port}",
            "--remote-allow-origins=*",
            f"--user-data-dir={self.user_data_dir}",
            "--no-first-run",
            "--no-default-browser-check",
            "--disable-gpu",
            "--window-size=1920,1080",
            "about:blank",
        ]
        if self.config.headless:
            args.insert(-1, "--headless=new")
        env = os.environ.copy()
        for key in (
            "HTTP_PROXY",
            "HTTPS_PROXY",
            "ALL_PROXY",
            "NO_PROXY",
            "http_proxy",
            "https_proxy",
            "all_proxy",
            "no_proxy",
        ):
            env.pop(key, None)
        self.browser_process = subprocess.Popen(args, env=env)
        self.logger.info("Chrome запущен для web UI теста.")

    def _pick_free_port(self) -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])

    def _resolve_browser_exe(self) -> str:
        candidates = [
            self.config.chrome_exe,
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        ]
        for candidate in candidates:
            if candidate and Path(candidate).exists():
                return candidate
        raise RuntimeError(f"Не найден браузер: {self.config.chrome_exe}")

    def _open_initial_target(self) -> None:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        version_info = None
        for _ in range(40):
            try:
                with opener.open(f"http://127.0.0.1:{self.debug_port}/json/version", timeout=2) as response:
                    version_info = json.load(response)
                break
            except Exception:
                time.sleep(0.5)
        if version_info is None:
            raise RuntimeError("Не удалось подключиться к Chrome DevTools Protocol.")
        self.websocket = websocket.create_connection(
            version_info["webSocketDebuggerUrl"],
            timeout=60,
            http_proxy_host=None,
            http_proxy_port=None,
            origin="http://127.0.0.1",
        )
        self.websocket.settimeout(60)
        target_id = self._browser_call("Target.createTarget", {"url": self.config.web_url})["result"]["targetId"]
        self.session_id = self._browser_call(
            "Target.attachToTarget",
            {"targetId": target_id, "flatten": True},
        )["result"]["sessionId"]
        self._session_call("Page.enable")
        self._session_call("Runtime.enable")
        self.logger.info("CDP-сессия подключена.")

    def _login(self) -> None:
        self.logger.info("Выполняем вход в web-client.")
        self._dismiss_startup_canvas_dialog()
        deadline = time.time() + 180
        initial_text = ""
        while time.time() < deadline:
            initial_text = self._safe_body_text()
            user_visible = self.config.user and self.config.user in initial_text
            admin_alias_visible = self.config.user == "Администратор" and "admin" in initial_text
            if user_visible or admin_alias_visible:
                self.logger.info("web-client уже открыт под нужным пользователем.")
                return
            if "Войти" in initial_text:
                break
            if "Не обнаружено свободной лицензии" in initial_text:
                raise RuntimeError("Веб-клиент не смог открыть базу: закончились свободные лицензии 1С.")
            time.sleep(3)
        if "Войти" not in initial_text:
            raise RuntimeError("Не найдена форма входа web-client и пользователь не обнаружен в рабочей области за 180 секунд.")
        login_js = """
(() => {
  const login = document.getElementById('authWindow_basic_login');
  const password = document.getElementById('authWindow_basic_password');
  const button = document.getElementById('authWindow_basic_okButton');
  if (!login || !password || !button) {
    return 'auth-controls-missing';
  }
  login.focus();
  login.value = %s;
  login.dispatchEvent(new Event('input', {bubbles:true}));
  login.dispatchEvent(new Event('change', {bubbles:true}));
  password.focus();
  password.value = %s;
  password.dispatchEvent(new Event('input', {bubbles:true}));
  password.dispatchEvent(new Event('change', {bubbles:true}));
  button.click();
  return 'submitted';
})()
""" % (json.dumps(self.config.user), json.dumps(self.config.password))
        result = self._evaluate(login_js)
        if result != "submitted":
            raise RuntimeError(f"Не удалось отправить форму входа: {result}")
        self.logger.info("Форма входа отправлена, ждём загрузку рабочей области.")
        time.sleep(20)
        self._wait_until_text_contains(self.config.user, 90)
        self.logger.info("Вход в web-client выполнен.")

    def _dismiss_startup_canvas_dialog(self) -> None:
        deadline = time.time() + 75
        while time.time() < deadline:
            try:
                text = self._safe_body_text().strip()
                if text and text != "\xa0":
                    return
                viewport = self._session_call(
                    "Runtime.evaluate",
                    {
                        "expression": "JSON.stringify({w: window.innerWidth || 800, h: window.innerHeight || 600})",
                        "returnByValue": True,
                    },
                )["result"]["result"].get("value", "{}")
                size = json.loads(str(viewport))
                x = int(float(size.get("w", 800)) * 0.875)
                y = int(float(size.get("h", 600)) * 0.72)
                for click_x, click_y in ((x, y), (670, 350)):
                    self._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": click_x, "y": click_y})
                    self._session_call(
                        "Input.dispatchMouseEvent",
                        {"type": "mousePressed", "x": click_x, "y": click_y, "button": "left", "clickCount": 1},
                    )
                    self._session_call(
                        "Input.dispatchMouseEvent",
                        {"type": "mouseReleased", "x": click_x, "y": click_y, "button": "left", "clickCount": 1},
                    )
                    time.sleep(1)
                time.sleep(5)
            except Exception:
                time.sleep(2)

    def _open_agent_command(self) -> None:
        self.logger.info("Пробуем открыть ИИ Агент через пункт меню.")
        if self._click_agent_theme_item() and self._wait_for_agent_form(20):
            return

        self.logger.info("Пробуем открыть ИИ Агент через кнопку Функции.")
        if self._click_functions_button() and self._click_any_visible_agent_candidate() and self._wait_for_agent_form(20):
            return

        self.logger.info("Пробуем открыть ИИ Агент через глобальный поиск.")
        if self._open_agent_via_global_search() and self._wait_for_agent_form(20):
            return

        self.logger.info("Переходим к команде ИИ Агент через hash-навигацию.")
        encoded_command = "CommonCommand.%D0%98%D0%98%D0%90_%D0%90%D0%B3%D0%B5%D0%BD%D1%82"
        target_url = self.config.web_url.rstrip("/") + f"/#e1cib/command/{encoded_command}"
        self._session_call("Page.navigate", {"url": target_url})
        if self._wait_for_agent_form(20):
            return

        raise RuntimeError("Форма ИИ Агент не открылась через web-client за отведённое время.")

    def _wait_for_agent_form(self, timeout_sec: int) -> bool:
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            text = self._safe_body_text()
            if "Не обнаружено свободной лицензии" in text:
                raise RuntimeError(
                    "Веб-клиент не смог открыть команду ИИ Агент: закончились свободные лицензии 1С."
                )
            if self._agent_form_visible():
                self.logger.info("Форма ИИ Агент открыта в web-client.")
                return True
            time.sleep(3)
        return False

    def _agent_form_visible(self) -> bool:
        js = """
(() => {
  const bodyText = (document.body && document.body.innerText || '').replace(/\\s+/g, ' ').trim();
  if ((bodyText.includes('Текущий диалог') && bodyText.includes('Отправить'))
      || bodyText.includes('Открыть форму запроса 1С')) {
    return true;
  }
  return false;
})()
"""
        result = self._evaluate(js)
        return result is True or str(result).lower() == "true"

    def _click_agent_theme_item(self) -> bool:
        js = """
(() => {
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 5 && r.height > 5 && r.x >= 0 && r.y >= 0
      && s.display !== 'none' && s.visibility !== 'hidden';
  };
  const click = (el) => {
    const r = el.getBoundingClientRect();
    ['pointerdown','mousedown','mouseup','click'].forEach((type) => {
      el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1, clientX:r.x + r.width / 2, clientY:r.y + r.height / 2}));
    });
  };
  const nodes = Array.from(document.querySelectorAll('a,button,div,span')).filter(visible)
    .map((el) => ({el, text:(el.innerText || el.title || '').replace(/\\s+/g, ' ').trim(), r:el.getBoundingClientRect()}));
  let command = nodes
    .filter((item) => item.text === 'ИИ Агент' && item.r.x > 190 && item.r.y > 70 && item.r.y < 180)
    .sort((a,b) => a.r.y - b.r.y)[0];
  if (command) {
    click(command.el);
    return JSON.stringify({result:'command-clicked', x: command.r.x + command.r.width / 2, y: command.r.y + command.r.height / 2});
  }
  const theme = nodes
    .filter((item) => item.text === 'ИИ Агент' && item.r.x < 180)
    .sort((a,b) => a.r.y - b.r.y)[0]?.el;
  if (!theme) return 'missing';
  click(theme);
  const r = theme.getBoundingClientRect();
  return JSON.stringify({result:'theme-clicked', x: r.x + r.width / 2, y: r.y + r.height / 2});
})()
"""
        first = self._evaluate(js)
        try:
            first_data = json.loads(str(first))
        except Exception:
            first_data = {"result": str(first or "")}
        if first_data.get("result") == "command-clicked":
            return True
        time.sleep(3)
        second = self._evaluate(js)
        try:
            second_data = json.loads(str(second))
        except Exception:
            second_data = {"result": str(second or "")}
        if second_data.get("result") == "command-clicked":
            return True
        for x, y in ((260, 112), (250, 112), (270, 112)):
            self._session_call("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
            self._session_call(
                "Input.dispatchMouseEvent",
                {"type": "mousePressed", "x": x, "y": y, "button": "left", "buttons": 1, "clickCount": 1},
            )
            self._session_call(
                "Input.dispatchMouseEvent",
                {"type": "mouseReleased", "x": x, "y": y, "button": "left", "buttons": 0, "clickCount": 1},
            )
            time.sleep(1)
        return True

    def _click_functions_button(self) -> bool:
        js = """
(() => {
  const el = document.getElementById('captionbarFunction');
  if (!el) return 'missing';
  ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach((type) => {
    el.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1}));
  });
  return 'clicked';
})()
"""
        return self._evaluate(js) == "clicked"

    def _click_any_visible_agent_candidate(self) -> bool:
        js = """
(() => {
  const items = Array.from(document.querySelectorAll('*'));
  const candidate = items.find((el) => {
    const text = (el.innerText || '').trim();
    if (text !== 'ИИ Агент') return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
  });
  if (!candidate) return 'missing';
  ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach((type) => {
    candidate.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1}));
  });
  return candidate.id || candidate.className || 'clicked';
})()
"""
        return self._evaluate(js) != "missing"

    def _open_agent_via_global_search(self) -> bool:
        fill_result = self._evaluate(
            """
(() => {
  const input = document.getElementById('captionbarField_i0');
  if (!input) return 'missing';
  input.focus();
  input.value = 'ИИ Агент';
  input.dispatchEvent(new Event('input', {bubbles:true}));
  input.dispatchEvent(new Event('change', {bubbles:true}));
  return 'filled';
})()
"""
        )
        if fill_result != "filled":
            return False
        time.sleep(5)
        click_result = self._evaluate(
            """
(() => {
  const items = Array.from(document.querySelectorAll('#dropdown .dropdownItem, #dropdown [data-role=\"item\"]'));
  const candidate = items.find((el) => (el.innerText || '').includes('ИИ Агент'));
  if (!candidate) return 'missing';
  ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach((type) => {
    candidate.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1}));
  });
  return candidate.innerText || 'clicked';
})()
"""
        )
        return click_result != "missing"

    def _assert_query1c_markers(self) -> None:
        text = self._body_text()
        if "Открыть форму запроса 1С" not in text and self.config.expected_text not in text:
            raise RuntimeError(
                "В форме web-client не найдены маркеры сценария Query1C "
                "('Открыть форму запроса 1С' или ожидаемый текст)."
            )

    def _open_query_form(self) -> None:
        self.logger.info("Открываем отдельную форму запроса по ссылке.")
        if not self._click_visible_text(["Открыть форму запроса 1С"]):
            raise RuntimeError("Не удалось нажать ссылку 'Открыть форму запроса 1С' в web-client.")
        self._wait_until_text_contains("Параметры запроса", 30)
        self._wait_until_text_contains("Результат", 30)
        self._wait_until_text_contains("Выполнить", 30)

    def _assert_parameter_table(self) -> None:
        text = self._body_text()
        for marker in ("Имя", "Тип", "Значение"):
            if marker not in text:
                raise RuntimeError(f"В форме запроса не найден заголовок колонки параметров: {marker!r}")
        params = self._parse_params_json()
        for key, value in params.items():
            expected_value = self._stringify_param_value(value)
            if key not in text:
                raise RuntimeError(f"В таблице параметров не найдено имя параметра: {key!r}")
            if expected_value and expected_value not in text:
                raise RuntimeError(
                    f"В таблице параметров не найдено ожидаемое значение {expected_value!r} для параметра {key!r}"
                )
            expected_type = self._detect_param_type_label(value)
            if expected_type not in text:
                raise RuntimeError(
                    f"В таблице параметров не найден ожидаемый тип {expected_type!r} для параметра {key!r}"
                )

    def _execute_query(self) -> None:
        self.logger.info("Выполняем запрос из отдельной формы.")
        if not self._click_visible_text(["Выполнить"]):
            raise RuntimeError("Не удалось нажать кнопку 'Выполнить' в форме запроса.")
        self._wait_until_any_text_contains(["Запрос выполнен.", self.config.expected_text], self.config.timeout_sec)
        body_text = self._body_text()
        if self.config.expected_text not in body_text:
            raise RuntimeError(
                f"После выполнения запроса не найден ожидаемый текст результата: {self.config.expected_text!r}"
            )

    def _click_visible_text(self, texts: list[str]) -> bool:
        expression = """
(() => {
  const variants = %s;
  const items = Array.from(document.querySelectorAll('*'));
  const candidate = items.find((el) => {
    const text = (el.innerText || '').trim();
    if (!variants.includes(text)) return false;
    const style = window.getComputedStyle(el);
    return style.display !== 'none' && style.visibility !== 'hidden' && el.offsetParent !== null;
  });
  if (!candidate) return 'missing';
  candidate.scrollIntoView({block: 'center'});
  ['pointerdown', 'mousedown', 'mouseup', 'click'].forEach((type) => {
    candidate.dispatchEvent(new MouseEvent(type, {bubbles:true, cancelable:true, view:window, buttons:1}));
  });
  return candidate.innerText || candidate.id || 'clicked';
})()
""" % json.dumps(texts, ensure_ascii=False)
        return self._evaluate(expression) != "missing"

    def _wait_until_any_text_contains(self, texts: list[str], timeout_sec: int) -> None:
        expected = [text.lower() for text in texts if text]
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                body_text = self._safe_body_text().lower()
            except Exception:
                time.sleep(2)
                continue
            for text in expected:
                if text in body_text:
                    return
            time.sleep(2)
        raise RuntimeError(f"Не найден ни один из ожидаемых текстов в web-client: {texts!r}")

    def _parse_params_json(self) -> dict[str, object]:
        raw = (self.config.query_params_json or "").strip()
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Тест получил некорректный query_params_json: {exc}") from exc
        if not isinstance(data, dict):
            raise RuntimeError("query_params_json должен быть JSON-объектом.")
        return data

    def _detect_param_type_label(self, value: object) -> str:
        if isinstance(value, bool):
            return "Булево"
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return "Число"
        if isinstance(value, str):
            return "Строка"
        return "JSON"

    def _stringify_param_value(self, value: object) -> str:
        if value is None:
            return ""
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def _browser_call(self, method: str, params: Optional[dict[str, object]] = None) -> dict[str, object]:
        self.message_id += 1
        payload = {"id": self.message_id, "method": method, "params": params or {}}
        self.websocket.send(json.dumps(payload))
        return self._recv_until(self.message_id)

    def _session_call(self, method: str, params: Optional[dict[str, object]] = None) -> dict[str, object]:
        self.message_id += 1
        payload = {
            "id": self.message_id,
            "sessionId": self.session_id,
            "method": method,
            "params": params or {},
        }
        self.websocket.send(json.dumps(payload))
        return self._recv_until(self.message_id)

    def _recv_until(self, expected_id: int) -> dict[str, object]:
        while True:
            try:
                message = json.loads(self.websocket.recv())
            except WebSocketTimeoutException:
                continue
            if message.get("method") == "Page.javascriptDialogOpening":
                self._accept_javascript_dialog()
                continue
            if message.get("id") == expected_id:
                return message

    def _accept_javascript_dialog(self) -> None:
        if self.websocket is None or not self.session_id:
            return
        self.message_id += 1
        payload = {
            "id": self.message_id,
            "sessionId": self.session_id,
            "method": "Page.handleJavaScriptDialog",
            "params": {"accept": True},
        }
        try:
            self.websocket.send(json.dumps(payload))
        except Exception:
            pass

    def _evaluate(self, expression: str) -> str:
        result = self._session_call(
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True},
        )
        return str(result["result"]["result"].get("value", ""))

    def _body_text(self) -> str:
        return self._evaluate('document.body ? document.body.innerText : ""')

    def _safe_body_text(self) -> str:
        last_error = None
        for _ in range(3):
            try:
                return self._body_text()
            except Exception as exc:
                last_error = exc
                time.sleep(3)
        raise last_error if last_error is not None else RuntimeError("Не удалось прочитать текст страницы.")

    def _wait_until_text_contains(self, text: str, timeout_sec: int) -> None:
        expected = text.lower()
        deadline = time.time() + timeout_sec
        while time.time() < deadline:
            try:
                body_text = self._safe_body_text()
            except Exception:
                time.sleep(2)
                continue
            if expected in body_text.lower():
                return
            time.sleep(2)
        raise RuntimeError(f"Не найден текст в web-client: {text!r}")

    def _capture_artifacts(self) -> None:
        if not self.config.artifact_dir:
            return
        target_dir = Path(self.config.artifact_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stamp = int(time.time())
        try:
            body_text = self._body_text()
            (target_dir / f"web_query1c_failure_{stamp}.txt").write_text(body_text, encoding="utf-8")
        except Exception as exc:
            self.logger.error(f"Не удалось сохранить текст страницы: {exc}")
        try:
            html = self._evaluate('document.body ? document.body.innerHTML : ""')
            (target_dir / f"web_query1c_failure_{stamp}.html").write_text(html, encoding="utf-8")
        except Exception as exc:
            self.logger.error(f"Не удалось сохранить HTML страницы: {exc}")

    def _close(self) -> None:
        try:
            if self.websocket is not None:
                self.websocket.close()
        except Exception:
            pass
        try:
            if self.browser_process is not None:
                self.browser_process.terminate()
                self.browser_process.wait(timeout=5)
        except Exception:
            try:
                if self.browser_process is not None:
                    self.browser_process.kill()
            except Exception:
                pass
        if self.user_data_dir:
            shutil.rmtree(self.user_data_dir, ignore_errors=True)


def parse_args() -> WebUiConfig:
    parser = argparse.ArgumentParser(description="Браузерный UI тест Query1C для web-client 1С")
    parser.add_argument("--web-url", default=DEFAULT_WEB_URL)
    parser.add_argument(
        "--chrome-exe",
        default=r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    )
    parser.add_argument("--base-path", default=DEFAULT_CONNECTION_STRING)
    parser.add_argument("--user", default="Администратор")
    parser.add_argument("--password", default="")
    parser.add_argument("--query-text", default="ВЫБРАТЬ 2 КАК Новое")
    parser.add_argument("--query-params-json", default="")
    parser.add_argument("--expected-text", default="Открыть форму запроса 1С")
    parser.add_argument("--timeout-sec", type=int, default=120)
    parser.add_argument(
        "--log-file",
        default=str(Path("automation") / "logs" / "web_query1c_test.log"),
    )
    parser.add_argument(
        "--artifact-dir",
        default=str(Path("automation") / "logs" / "web_query1c_artifacts"),
    )
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--skip-com-prepare", action="store_true")
    args = parser.parse_args()
    return WebUiConfig(
        web_url=args.web_url,
        chrome_exe=args.chrome_exe,
        base_path=args.base_path,
        user=args.user,
        password=args.password,
        query_text=args.query_text,
        query_params_json=args.query_params_json,
        expected_text=args.expected_text,
        timeout_sec=args.timeout_sec,
        log_file=args.log_file,
        artifact_dir=args.artifact_dir,
        headless=not args.headed,
        skip_com_prepare=args.skip_com_prepare,
    )


def main() -> int:
    setup_console_encoding()
    config = parse_args()
    logger = Logger(config.log_file)
    return BrowserQuery1CTest(config, logger).run()


if __name__ == "__main__":
    raise SystemExit(main())
