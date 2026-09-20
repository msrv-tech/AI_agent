# -*- coding: utf-8 -*-
"""Upload a Fresh CFE as a new version in 1C:Fresh service manager."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


DEFAULT_ADM_URL = "https://1cfresh.com/a/adm/ru_RU/"
DEFAULT_EXTENSION_TITLE = "ИИ агент"
REQUIRED_HOSTS = (
    "gitsell.ru",
    "api.giga.chat",
    "ngw.devices.sberbank.ru",
    "ai.api.cloud.yandex.net",
)
WIZARD_TITLES = (
    "загрузка файла",
    "отличающихся полей",
    "сведения о расширении",
    "защита исходного кода",
    "защита исходного",
    "совместимость",
    "требуемые разрешения",
    "заполните описание изменения",
    "описание изменения",
    "автоматическая проверка",
)


VISIBLE_JS = r"""
([text, exact, insideMarker]) => {
  const needle = (text || "").trim();
  const visible = (el) => {
    const r = el.getBoundingClientRect();
    const s = getComputedStyle(el);
    return r.width > 4 && r.height > 4 && r.x > -1000 && r.y > -1000
      && s.display !== "none" && s.visibility !== "hidden" && s.opacity !== "0";
  };
  const topmost = (x, y, el) => {
    const top = document.elementFromPoint(x, y);
    return top && (top === el || el.contains(top) || (top && top.contains(el)));
  };
  let box = null;
  if (insideMarker) {
    const mark = Array.from(document.querySelectorAll("button, a, span, div, td, label")).find((el) => {
      if (!visible(el)) return false;
      const value = ((el.innerText || el.value || "")).replace(/\s+/g, " ").trim();
      return value === insideMarker;
    });
    if (mark) {
      let host = mark;
      while (host && host.parentElement && host.getBoundingClientRect().width < 520) {
        host = host.parentElement;
      }
      box = host ? host.getBoundingClientRect() : null;
    }
  }
  const nodes = Array.from(document.querySelectorAll("button, a, span, div, td, th, label, input"));
  const matches = [];
  for (const el of nodes) {
    if (!visible(el)) continue;
    const r = el.getBoundingClientRect();
    if (box && (r.left < box.left - 4 || r.right > box.right + 4 || r.top < box.top - 4 || r.bottom > box.bottom + 4)) {
      continue;
    }
    const value = ((el.innerText || el.value || el.title || "")).replace(/\s+/g, " ").trim();
    if (!value) continue;
    if (exact ? value === needle : value.includes(needle)) {
      const x = r.left + r.width / 2;
      const y = r.top + r.height / 2;
      if (!box && !topmost(x, y, el)) continue;
      matches.push({x, y, w: r.width, h: r.height, text: value});
    }
  }
  if (!matches.length) return null;
  matches.sort((a, b) => (a.w * a.h) - (b.w * b.h));
  return matches[0];
}
"""


class FreshUploadError(RuntimeError):
    pass


def _require_playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise FreshUploadError(
            "Нет пакета playwright. Установите: pip install -r automation/ops/requirements-fresh.txt "
            "&& python -m playwright install chromium"
        ) from exc
    return sync_playwright


class FreshServiceManager:
    def __init__(self, page, artifact_dir: Path, timeout_ms: int) -> None:
        self.page = page
        self.artifact_dir = artifact_dir
        self.timeout_ms = timeout_ms
        self.steps: list[str] = []

    def note(self, message: str) -> None:
        self.steps.append(message)
        print(message, flush=True)

    def screenshot(self, name: str) -> Path:
        path = self.artifact_dir / f"{name}.png"
        self.page.screenshot(path=str(path), full_page=True)
        return path

    def body_text(self) -> str:
        visible = (self.page.inner_text("body") or "").replace("\xa0", " ")
        try:
            nodes = self.page.evaluate(
                """
                () => {
                  if (!document.body) return "";
                  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
                  const out = [];
                  while (walker.nextNode()) {
                    const text = (walker.currentNode.textContent || "").replace(/\\s+/g, " ").trim();
                    if (text) out.push(text);
                  }
                  return out.join("\\n");
                }
                """
            )
        except Exception:
            nodes = ""
        return visible + "\n" + (nodes or "")

    def wait_text(self, *needles: str, timeout_ms: int | None = None) -> str:
        deadline = time.time() + ((timeout_ms or self.timeout_ms) / 1000)
        last = ""
        while time.time() < deadline:
            last = self.body_text()
            if any(needle in last for needle in needles):
                return last
            self.page.wait_for_timeout(500)
        raise FreshUploadError(f"Не появилось ни одно из: {needles}. Сейчас: {last[:500]}")

    def visible_box(self, text: str, exact: bool = True, inside: str = "") -> dict[str, Any] | None:
        return self.page.evaluate(VISIBLE_JS, [text, exact, inside])

    def visible_text_node(self, text: str, exact: bool = True) -> dict[str, Any] | None:
        return self.page.evaluate(
            """
            ([needle, exact]) => {
              const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
              const hits = [];
              while (walker.nextNode()) {
                const raw = (walker.currentNode.textContent || "").replace(/\\s+/g, " ").trim();
                if (!raw) continue;
                if (exact ? raw !== needle : !raw.includes(needle)) continue;
                const el = walker.currentNode.parentElement;
                if (!el) continue;
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                if (r.width < 2 || r.height < 2 || s.display === "none" || s.visibility === "hidden") continue;
                hits.push({
                  x: r.left + r.width / 2,
                  y: r.top + r.height / 2,
                  w: r.width,
                  h: r.height,
                  text: raw,
                });
              }
              if (!hits.length) return null;
              hits.sort((a, b) => (a.w * a.h) - (b.w * b.h));
              return hits[0];
            }
            """,
            [text, exact],
        )

    def click_text(self, text: str, exact: bool = True, inside: str = "") -> None:
        box = self.visible_box(text, exact=exact, inside=inside)
        if box is None:
            box = self.visible_text_node(text, exact=exact)
        if box is None:
            self.screenshot("missing_" + re_slug(text))
            raise FreshUploadError(f"Не найден видимый элемент «{text}»")
        self.page.mouse.click(box["x"], box["y"])

    def type_into_focused(self, value: str) -> None:
        self.page.keyboard.press("Control+A")
        self.page.keyboard.type(value, delay=15)

    def visible_page_text(self) -> str:
        return (self.page.inner_text("body") or "").replace("\xa0", " ")

    def wizard_title(self) -> str:
        if (
            self.visible_box("Выполняется автоматическая проверка", exact=False)
            or self.visible_text_node("Выполняется автоматическая проверка", exact=False)
            or self.visible_box("Автоматическая проверка", exact=False)
        ):
            return "автоматическая проверка"
        if self.visible_box("Включить защиту исходного кода") or self.visible_text_node("Включить защиту исходного кода"):
            return "защита исходного кода"
        if self.visible_box("Почта разработчика") or self.visible_text_node("Почта разработчика"):
            return "адреса"
        if self.visible_box("Интернет-ресурсы") or self.visible_text_node("gitsell.ru"):
            if self.visible_box("Привилегированный режим") or self.visible_text_node("Привилегированный режим"):
                return "требуемые разрешения"
        if self.visible_box("Заполните описание изменения") or self.visible_text_node("Заполните описание изменения"):
            return "описание изменения"
        if self.visible_box("Краткая информация") or self.visible_text_node("Краткая информация"):
            return "сведения о расширении"
        visible = self.visible_page_text().lower()
        for title in WIZARD_TITLES:
            if title in visible:
                return title
            if self.visible_text_node(title, exact=False):
                return title
        return ""

    def login_openid(self, user: str, password: str) -> None:
        if not user or not password:
            raise FreshUploadError("Для входа в 1С:Фреш задайте FRESH_CLOUD_USER и FRESH_CLOUD_PASSWORD.")
        self.wait_text("Пользователь", "Вход в сервис", "Адаптация", "Менеджер сервиса")
        current = self.body_text()
        if "Адаптация" in current or "Менеджер сервиса" in current:
            self.note("Сессия Менеджера сервиса уже открыта.")
            return
        submitted = self.page.evaluate(
            """
            ([user, password]) => {
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 20 && r.height > 10 && s.display !== "none" && s.visibility !== "hidden";
              };
              const byPlaceholder = (value) => Array.from(document.querySelectorAll("input")).find(
                (el) => visible(el) && (el.placeholder || "").trim() === value
              );
              const login = byPlaceholder("Пользователь") || document.querySelector("input[type='text'], input:not([type])");
              const secret = byPlaceholder("Пароль") || document.querySelector("input[type='password']");
              const button = Array.from(document.querySelectorAll("button")).find(
                (el) => visible(el) && (el.innerText || "").trim() === "Войти"
              );
              if (!login || !secret || !button) return "auth-controls-missing";
              const setValue = (el, value) => {
                el.focus();
                el.value = value;
                el.dispatchEvent(new Event("input", {bubbles: true}));
                el.dispatchEvent(new Event("change", {bubbles: true}));
              };
              setValue(login, user);
              setValue(secret, password);
              button.click();
              return "submitted";
            }
            """,
            [user, password],
        )
        if submitted != "submitted":
            self.screenshot("openid_missing")
            raise FreshUploadError(f"Не удалось отправить OpenID-форму: {submitted}")
        self.note("OpenID-форма отправлена.")
        self.wait_text(
            "Добавить из файла",
            "Адаптация приложений",
            "Менеджер сервиса",
            timeout_ms=max(self.timeout_ms, 120000),
        )

    def on_extensions_list(self) -> bool:
        text = self.body_text()
        return "Добавить из файла" in text and "Проверить расширение из файла" in text

    def open_adaptations(self) -> None:
        if self.on_extensions_list():
            self.note("Список расширений уже открыт.")
            self.screenshot("extensions_list")
            return
        if self.visible_box("Адаптация приложений"):
            self.click_text("Адаптация приложений")
        elif self.visible_box("Адаптация", exact=False):
            self.click_text("Адаптация", exact=False)
        else:
            self.screenshot("no_adaptations")
            raise FreshUploadError("Не найдена команда «Адаптация приложений».")
        self.wait_text("Добавить из файла", "Проверить расширение из файла")
        if not self.on_extensions_list():
            if self.visible_box("Расширения"):
                self.click_text("Расширения")
            self.wait_text("Добавить из файла", "Проверить расширение из файла")
        if not self.on_extensions_list():
            self.screenshot("extensions_list_missing")
            raise FreshUploadError("После открытия адаптации нет списка расширений.")
        self.screenshot("extensions_list")

    def card_opened(self) -> bool:
        text = self.body_text()
        return "Описания расширения" in text or "Расширение конфигурации" in text or (
            "Опубликовано" in text and "ИИ_Агент" in text
        )

    def close_start_page(self) -> None:
        box = self.visible_box("Начальная страница")
        if box is None:
            return
        self.page.mouse.click(box["x"], box["y"], button="right")
        self.page.wait_for_timeout(400)
        if self.visible_box("Закрыть"):
            self.note("Закрываю начальную страницу, чтобы не перехватывать фокус.")
            self.click_text("Закрыть")
            self.page.wait_for_timeout(600)

    def close_form(self) -> None:
        if self.visible_box("Закрыть"):
            self.click_text("Закрыть")
            self.page.wait_for_timeout(800)
        elif self.visible_box("Записать и закрыть"):
            self.click_text("Записать и закрыть")
            self.page.wait_for_timeout(800)

    def open_extension(self, title: str) -> None:
        if title not in self.body_text():
            self.screenshot("extension_not_found")
            raise FreshUploadError(f"Расширение «{title}» не найдено в списке Менеджера сервиса.")
        row = self.visible_box(title, exact=True)
        if row is None:
            row = self.visible_box(title, exact=False)
        if row is None:
            raise FreshUploadError(f"Строка «{title}» не видима в списке.")
        self.note(f"Открываю карточку «{title}».")
        self.page.mouse.click(row["x"], row["y"])
        self.page.wait_for_timeout(400)
        opened = False
        if self.visible_box("Еще"):
            self.click_text("Еще")
            self.page.wait_for_timeout(400)
            if self.visible_box("Изменить"):
                self.click_text("Изменить")
                self.page.wait_for_timeout(2000)
                opened = True
        if not opened:
            self.page.mouse.dblclick(row["x"], row["y"])
            self.page.wait_for_timeout(2000)
        self.take_over_lock_if_needed(required=False)
        if not self.card_opened():
            self.screenshot("extension_card_missing")
            raise FreshUploadError(f"Карточка «{title}» не открылась после выбора строки.")
        self.screenshot("extension_card")

    def recover_stale_lock(self, title: str) -> None:
        self.close_start_page()
        try:
            self.open_extension(title)
        except FreshUploadError as exc:
            self.note(f"Карточка для перехвата не открылась: {exc}")
            self.screenshot("recover_card_failed")
            return
        self.take_over_lock_if_needed(required=False)
        if not self.card_opened():
            return
        self.note("Карточка открыта — снимаю чужую блокировку и закрываю форму.")
        self.take_over_lock_if_needed(required=False, wait_sec=3)
        if self.visible_box("Записать и закрыть"):
            self.click_text("Записать и закрыть")
            self.page.wait_for_timeout(800)
        self.take_over_lock_if_needed(required=False, wait_sec=10)
        if self.visible_box("Записать и закрыть") and not self.visible_box("Перехватить редактирование"):
            self.click_text("Записать и закрыть")
            self.page.wait_for_timeout(1200)
        if self.visible_box("Да"):
            self.click_text("Да")
            self.page.wait_for_timeout(800)
        self.screenshot("card_closed")
        if self.card_opened():
            self.note("Карточка не закрылась, продолжаю загрузку с открытой формой.")
        elif not self.on_extensions_list():
            self.open_adaptations()

    def take_over_lock_if_needed(self, required: bool = True, wait_sec: float = 0) -> None:
        deadline = time.time() + max(wait_sec, 0)
        while True:
            if self.visible_box("Перехватить редактирование"):
                self.note("Перехватываю блокировку своего предыдущего сеанса.")
                self.click_text("Перехватить редактирование")
                self.page.wait_for_timeout(1500)
                return
            text = self.body_text()
            locked = "уже заблокирован" in text or "Не удалось начать редактирование" in text
            if time.time() >= deadline:
                if locked and required:
                    raise FreshUploadError(
                        "Объект заблокирован другим сеансом 1С:Фреш. "
                        "Закройте лишний веб-клиент Менеджера сервиса и повторите деплой."
                    )
                return
            self.page.wait_for_timeout(400)

    def start_new_version_from_list(self) -> None:
        if not self.visible_box("Добавить из файла..."):
            raise FreshUploadError("В списке расширений нет команды «Добавить из файла...».")
        self.note("Запускаю «Добавить из файла...» для новой версии.")
        self.click_text("Добавить из файла...")
        self.wait_text("Загрузка файла", "Файл расширения", "Выбрать с диска")
        self.screenshot("wizard_upload")

    def versions_tab_opened(self) -> bool:
        text = self.body_text()
        markers = (
            "Загрузить расширение из файла",
            "Номер версии",
            "Дата загрузки",
            "Используется в приложениях",
            "Описание изменения",
        )
        return any(marker in text for marker in markers)

    def probe_versions_tab(self, published: dict[str, Any]) -> dict[str, Any] | None:
        row = self.page.evaluate(
            """
            (y) => Array.from(document.querySelectorAll('*')).map((el) => {
              const r = el.getBoundingClientRect();
              const s = getComputedStyle(el);
              if (r.width < 20 || r.height < 8 || r.height > 36) return null;
              if (Math.abs((r.top + r.height / 2) - y) > 14) return null;
              if (s.display === 'none' || s.visibility === 'hidden') return null;
              const text = ((el.innerText || el.textContent || '')).replace(/\\s+/g, ' ').trim();
              return {x: r.left + r.width / 2, y: r.top + r.height / 2, w: r.width, h: r.height, text};
            }).filter(Boolean)
            """,
            published["y"],
        )
        (self.artifact_dir / "tab_row.json").write_text(
            json.dumps(row, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        for item in row:
            if item.get("text") in {"Версии", "Версия"}:
                return item
        for offset in (200, 230, 260, 290, 320, 170):
            point = {
                "x": published["x"] + (published["w"] / 2) + offset,
                "y": published["y"],
                "w": 40,
                "h": 18,
            }
            self.page.mouse.click(point["x"], point["y"])
            self.page.wait_for_timeout(900)
            if self.versions_tab_opened():
                self.note(f"Вкладка «Версии» открыта по смещению {offset}.")
                return point
        return None

    def start_new_version(self) -> None:
        versions = (
            self.visible_box("Версии")
            or self.visible_text_node("Версии")
        )
        if versions is None:
            versions = (
                self.visible_box("Версии", exact=False)
                or self.visible_text_node("Версии", exact=False)
            )
        if versions is None:
            published = self.visible_box("Опубликовано")
            if published is None:
                published = self.visible_text_node("Опубликовано")
            if published is not None:
                self.note("Вкладка «Версии» без DOM-текста, подбираю клик по ряду вкладок.")
                versions = self.probe_versions_tab(published)
        if versions is None:
            labels = self.page.evaluate(
                """
                () => Array.from(new Set(Array.from(document.querySelectorAll('button,a,span,div,td,label'))
                  .map((el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    if (r.width < 8 || r.height < 8 || s.display === 'none') return '';
                    return ((el.innerText || el.value || '')).replace(/\\s+/g, ' ').trim();
                  })
                  .filter((t) => t && t.length < 60)))
                """
            )
            (self.artifact_dir / "visible_labels.json").write_text(
                json.dumps(labels, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            self.screenshot("no_versions_tab")
            raise FreshUploadError("На карточке расширения нет вкладки «Версии».")
        if not self.versions_tab_opened():
            self.note("Открываю вкладку «Версии».")
            self.page.mouse.click(versions["x"], versions["y"])
            self.page.wait_for_timeout(1200)
        self.screenshot("versions_tab")
        if not self.versions_tab_opened():
            self.screenshot("versions_tab_wrong")
            raise FreshUploadError("Клик не открыл вкладку «Версии».")
        if self.visible_box("Загрузить расширение из файла") or self.visible_text_node("Загрузить расширение из файла"):
            self.click_text("Загрузить расширение из файла")
        elif self.visible_box("Загрузить из файла", exact=False) or self.visible_text_node("Загрузить из файла", exact=False):
            self.click_text("Загрузить из файла", exact=False)
        else:
            more = self.visible_box("Еще...") or self.visible_text_node("Еще...")
            if more is None:
                more = self.visible_box("Еще")
            if more is None:
                self.screenshot("no_upload_command")
                raise FreshUploadError("На вкладке «Версии» нет команды загрузки файла.")
            self.page.mouse.click(more["x"], more["y"])
            self.page.wait_for_timeout(500)
            self.screenshot("versions_more")
            if self.visible_box("Загрузить расширение из файла", exact=False) or self.visible_text_node("Загрузить расширение из файла", exact=False):
                self.click_text("Загрузить расширение из файла", exact=False)
            elif self.visible_box("Загрузить из файла", exact=False) or self.visible_text_node("Загрузить из файла", exact=False):
                self.click_text("Загрузить из файла", exact=False)
            else:
                self.screenshot("no_upload_command")
                raise FreshUploadError("В меню карточки нет команды загрузки файла.")
        self.wait_text("Загрузка файла", "Файл расширения", "Выбрать с диска")
        self.screenshot("wizard_upload")

    def upload_cfe(self, cfe_path: Path) -> None:
        field = self.visible_box("Выберите файл", exact=False)
        if field is None:
            self.screenshot("file_field_missing")
            raise FreshUploadError("В мастере нет поля «Выберите файл».")
        self.page.mouse.click(field["x"] + (field["w"] / 2) + 20, field["y"])
        self.wait_text("Выбрать с диска", "Загрузка файла в сервис")
        self.screenshot("file_service_dialog")
        try:
            with self.page.expect_file_chooser(timeout=8000) as pending:
                self.click_text("Выбрать с диска")
                pending.value.set_files(str(cfe_path))
        except Exception as exc:
            file_input = self.page.query_selector("#fileSelectInput")
            if file_input is None:
                self.screenshot("file_input_missing")
                raise FreshUploadError(f"Не удалось выбрать файл с диска: {exc}") from exc
            file_input.set_input_files(str(cfe_path))
        if self.visible_box("Загрузить"):
            self.click_text("Загрузить")
        elif self.page.query_selector("#fileSelectDialogOk"):
            self.page.click("#fileSelectDialogOk")
        else:
            raise FreshUploadError("После выбора файла нет кнопки «Загрузить».")
        self.page.wait_for_timeout(1500)
        selected = self.page.evaluate(
            """
            (name) => Array.from(document.querySelectorAll('input, textarea')).some(
              (el) => ((el.value || el.innerText || '')).includes(name)
            )
            """,
            cfe_path.name,
        )
        if not selected:
            selected = bool(
                self.visible_box(cfe_path.name, exact=False)
                or self.visible_text_node(cfe_path.name, exact=False)
                or self.visible_text_node(".cfe", exact=False)
            )
        nested_open = bool(self.visible_box("Выбрать с диска") or self.visible_box("Загрузка файла в сервис"))
        if not selected and nested_open:
            self.screenshot("upload_not_accepted")
            raise FreshUploadError(f"После выбора файла поле всё ещё пустое: {cfe_path.name}.")
        if not selected:
            self.note(f"Имя файла не в DOM, но диалог выбора закрыт — продолжаю с {cfe_path.name}.")
        self.screenshot("file_selected")
        self.take_over_lock_if_needed()
        if self.visible_box("Далее"):
            self.click_text("Далее")
        elif self.visible_box("Далее", exact=False):
            self.click_text("Далее", exact=False)
        else:
            raise FreshUploadError("После выбора файла нет кнопки «Далее».")
        self.wait_text("отличающихся", "Сведения о расширении", "Защита исходного", "Совместимость", "новая версия")

    def fill_changelog(self, changelog: str) -> None:
        area = self.page.evaluate(
            """
            () => {
              const visible = (el) => {
                const r = el.getBoundingClientRect();
                const s = getComputedStyle(el);
                return r.width > 80 && r.height > 20 && s.display !== "none" && s.visibility !== "hidden";
              };
              const node = Array.from(document.querySelectorAll("textarea, input")).find(visible);
              if (!node) return null;
              const r = node.getBoundingClientRect();
              return {x: r.left + r.width / 2, y: r.top + r.height / 2};
            }
            """
        )
        if area is None:
            self.screenshot("changelog_field_missing")
            raise FreshUploadError("На шаге изменений нет видимого поля описания.")
        self.page.mouse.click(area["x"], area["y"])
        self.type_into_focused(changelog)
        self.page.keyboard.press("Tab")
        self.screenshot("changelog_filled")

    def fill_fresh_addresses(self) -> None:
        if self.visible_box("Показать все", exact=False):
            self.click_text("Показать все", exact=False)
            self.page.wait_for_timeout(600)
            self.screenshot("address_messages")
        pairs = (
            ("Сайт расширения", "https://github.com/msrv-tech/AI_agent"),
            ("Сайт поставщика", "https://gitsell.ru"),
        )
        for kind, url in pairs:
            box = self.visible_box(kind) or self.visible_text_node(kind)
            if box is None:
                continue
            self.page.mouse.click(box["x"] + 250, box["y"])
            self.page.wait_for_timeout(300)
            self.type_into_focused(url)
            self.page.keyboard.press("Tab")
            self.page.wait_for_timeout(200)
        self.screenshot("addresses_filled")

    def ensure_source_protection_ready(self) -> None:
        body = self.visible_page_text()
        if "невозмож" not in body:
            return
        self.note("Защита модулей не настроена — открываю настройку, чтобы отключить её.")
        if self.visible_box("Показать все", exact=False):
            self.click_text("Показать все", exact=False)
            self.page.wait_for_timeout(500)
            self.screenshot("protection_messages")
        link = (
            self.visible_box("Защита модулей не настроена. Настроить")
            or self.visible_text_node("Настроить")
            or self.visible_box("Настроить")
        )
        if link is not None:
            self.page.mouse.click(link["x"] + max(link["w"] / 2 - 8, 10), link["y"])
            self.page.wait_for_timeout(1200)
            self.screenshot("protection_setup")
            labels = self.page.evaluate(
                """
                () => Array.from(new Set(Array.from(document.querySelectorAll('button,a,span,div,td,label'))
                  .map((el) => {
                    const r = el.getBoundingClientRect();
                    const s = getComputedStyle(el);
                    if (r.width < 6 || r.height < 6 || s.display === 'none') return '';
                    return ((el.innerText || el.value || '')).replace(/\\s+/g, ' ').trim();
                  })
                  .filter((t) => t && t.length < 80)))
                """
            )
            (self.artifact_dir / "protection_setup_labels.json").write_text(
                json.dumps(labels, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            for label in (
                "Отключить защиту",
                "Отключить",
                "Без защиты",
                "Снять защиту",
                "Очистить",
            ):
                if self.visible_box(label, exact=False):
                    self.click_text(label, exact=False)
                    self.page.wait_for_timeout(500)
                    break
            if self.visible_box("ОК"):
                self.click_text("ОК")
            elif self.visible_box("Записать и закрыть"):
                self.click_text("Записать и закрыть")
            elif self.visible_box("Закрыть"):
                self.click_text("Закрыть")
            self.page.wait_for_timeout(800)
            self.screenshot("protection_setup_done")
        elif self.visible_box("Включить защиту исходного кода"):
            self.click_text("Включить защиту исходного кода")
            self.page.wait_for_timeout(400)
            if self.visible_box("Включить защиту исходного кода"):
                self.click_text("Включить защиту исходного кода")
                self.page.wait_for_timeout(400)

    def assert_required_hosts(self) -> None:
        text = self.body_text()
        missing = [host for host in REQUIRED_HOSTS if host not in text]
        if missing:
            self.screenshot("permissions_missing_hosts")
            raise FreshUploadError("В разрешениях нет обязательных хостов: " + ", ".join(missing))

    def walk_wizard(self, version: str, changelog: str, finish: bool) -> None:
        seen: list[str] = []
        for index in range(16):
            title = self.wizard_title()
            body = self.body_text()
            self.note(f"Шаг мастера {index + 1}: {title or 'не распознан'}")
            self.screenshot(f"wizard_{index + 1:02d}")
            if "Не удалось начать редактирование" in body:
                if self.visible_box("Перехватить редактирование"):
                    self.click_text("Перехватить редактирование")
                    self.page.wait_for_timeout(1000)
                    continue
                raise FreshUploadError("Карточка занята другим сеансом, перехват недоступен.")
            if title == "загрузка файла":
                raise FreshUploadError("Мастер снова на загрузке файла после выбора CFE.")
            if title == "отличающихся полей":
                if self.visible_box("Новая"):
                    self.click_text("Новая")
                self.click_text("Далее")
                continue
            if title == "сведения о расширении":
                if version not in body and version not in self.visible_page_text():
                    raise FreshUploadError(f"В сведениях нет версии {version}.")
                self.click_text("Далее")
                self.page.wait_for_timeout(1200)
                continue
            if title in {"защита исходного кода", "защита исходного"}:
                if "невозмож" in self.visible_page_text():
                    self.ensure_source_protection_ready()
                self.click_text("Далее")
                self.page.wait_for_timeout(1200)
                continue
            if title == "совместимость":
                self.click_text("Далее")
                continue
            if title == "требуемые разрешения":
                self.assert_required_hosts()
                self.click_text("Далее")
                continue
            if title == "адреса":
                self.fill_fresh_addresses()
                if self.visible_box("Завершить"):
                    self.click_text("Завершить")
                else:
                    self.click_text("Далее")
                self.page.wait_for_timeout(1500)
                continue
            if title in {"заполните описание изменения", "описание изменения"}:
                if "Заполните описание изменения" in body or "описание изменения" in body.lower():
                    self.fill_changelog(changelog)
                elif changelog.splitlines()[0][2:20] not in body:
                    self.fill_changelog(changelog)
                if not finish:
                    self.note("Черновик: останов перед завершением мастера.")
                    return
                if self.visible_box("Завершить"):
                    self.click_text("Завершить")
                else:
                    self.click_text("Далее")
                continue
            if title == "автоматическая проверка":
                deadline = time.time() + 180
                while time.time() < deadline:
                    visible = self.visible_page_text()
                    if "Задача выполнена" in visible or "будет загружена новая версия" in visible:
                        self.screenshot("wizard_done")
                        return
                    self.page.wait_for_timeout(1000)
                self.screenshot("autocheck_timeout")
                raise FreshUploadError("Автоматическая проверка не завершилась за 180 сек.")
            if title in seen[-2:]:
                raise FreshUploadError(f"Мастер зациклился на шаге «{title}».")
            seen.append(title)
            raise FreshUploadError(f"Непонятный шаг мастера: {title or body[:300]}")
        raise FreshUploadError("Мастер не завершился за 16 шагов.")


def re_slug(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() else "_" for ch in value.lower())
    return (cleaned[:40] or "item")


def upload_fresh_version(
    *,
    cfe_path: Path,
    version: str,
    changelog: str,
    adm_url: str,
    extension_title: str,
    user: str,
    password: str,
    artifact_dir: Path,
    headed: bool,
    finish: bool,
    auth_state: Path | None,
    timeout_sec: int,
) -> dict[str, Any]:
    sync_playwright = _require_playwright()
    artifact_dir.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "adm_url": adm_url,
        "extension_title": extension_title,
        "cfe": str(cfe_path),
        "version": version,
        "finished": False,
        "steps": [],
    }
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not headed)
        context_kwargs: dict[str, Any] = {
            "locale": "ru-RU",
            "viewport": {"width": 1600, "height": 950},
            "ignore_https_errors": True,
        }
        if auth_state is not None:
            if not auth_state.is_file():
                raise FreshUploadError(f"Нет storage state: {auth_state}")
            context_kwargs["storage_state"] = str(auth_state)
        context = browser.new_context(**context_kwargs)
        context.grant_permissions(["clipboard-read", "clipboard-write"])
        page = context.new_page()
        session = FreshServiceManager(page, artifact_dir, timeout_sec * 1000)
        try:
            page.goto(adm_url, wait_until="domcontentloaded", timeout=timeout_sec * 1000)
            session.screenshot("adm_open")
            if auth_state is None:
                session.login_openid(user, password)
            else:
                session.wait_text("Адаптация", "Менеджер сервиса", "Пользователь")
                if "Пользователь" in session.body_text() and "Адаптация" not in session.body_text():
                    session.login_openid(user, password)
            session.open_adaptations()
            if extension_title not in session.body_text():
                raise FreshUploadError(f"Расширение «{extension_title}» не найдено в списке Менеджера сервиса.")
            session.recover_stale_lock(extension_title)
            if session.card_opened():
                session.start_new_version()
            else:
                session.start_new_version_from_list()
            session.upload_cfe(cfe_path)
            session.walk_wizard(version, changelog, finish)
            report["finished"] = finish
            report["steps"] = session.steps
        except Exception:
            session.screenshot("error")
            report["steps"] = session.steps
            (artifact_dir / "error_body.txt").write_text(session.body_text(), encoding="utf-8")
            raise
        finally:
            (artifact_dir / "upload_report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            context.close()
            browser.close()
    return report
