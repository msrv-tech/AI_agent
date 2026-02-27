# -*- coding: utf-8 -*-
"""
Модуль для отправки предложений в Telegram и ожидания одобрения.

Использует TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID из .env.
"""

import os
import json
import time
import urllib.request
import urllib.error
import urllib.parse

try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass


def _get_token_chat():
    """Возвращает (token, chat_id) или (None, None)."""
    return (
        os.environ.get("TELEGRAM_BOT_TOKEN"),
        os.environ.get("TELEGRAM_CHAT_ID"),
    )


def _api_request(token: str, method: str, data: dict = None) -> dict:
    """Выполняет запрос к Telegram Bot API."""
    url = f"https://api.telegram.org/bot{token}/{method}"
    if data:
        body = urllib.parse.urlencode(data).encode("utf-8")
        req = urllib.request.Request(url, data=body, method="POST")
    else:
        req = urllib.request.Request(url, method="GET")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    with urllib.request.urlopen(req, timeout=35) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _delete_webhook(token: str) -> bool:
    """Удаляет webhook — getUpdates не работает, пока webhook активен."""
    try:
        _api_request(token, "deleteWebhook", {})
        return True
    except Exception:
        return False


def _chat_matches(update_chat_id, expected_chat_id: str) -> bool:
    """Сравнивает chat_id (int/str)."""
    if update_chat_id is None:
        return False
    try:
        return int(update_chat_id) == int(expected_chat_id)
    except (TypeError, ValueError):
        return str(update_chat_id) == str(expected_chat_id)


def send_message(text: str, reply_markup: dict = None) -> bool:
    """Отправляет сообщение в Telegram. Возвращает True при успехе."""
    token, chat_id = _get_token_chat()
    if not token or not chat_id:
        return False
    try:
        data = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            data["reply_markup"] = json.dumps(reply_markup)
        _api_request(token, "sendMessage", data)
        return True
    except Exception:
        return False


def send_raw_analysis(
    run_id: str,
    raw_output: str,
    total_tokens: int = 0,
    cost_rub: float = 0,
    failed_ids: list = None,
) -> bool:
    """
    Отправляет сырой анализ в Telegram (без парсинга).

    raw_output: полный вывод агента. Разбивается на части по 4000 символов (лимит Telegram 4096).
    """
    token, chat_id = _get_token_chat()
    if not token or not chat_id:
        return False

    header = (
        f"<b>Анализ провалов</b>\n"
        f"Run: <code>{run_id}</code>\n"
    )
    if failed_ids:
        header += f"Провалившиеся: {', '.join(failed_ids)}\n"
    if total_tokens or cost_rub:
        header += f"Токены: {total_tokens:,} | Стоимость: ~{cost_rub} ₽\n"
    header += "\nОтветьте: «принять», «отклонить» или комментарий.\n\n"

    # Сырой вывод — escape для HTML, разбить по 3800 символов (лимит 4096 с header)
    import html
    raw_escaped = html.escape(raw_output.strip())
    chunk_size = 3800
    chunks = [raw_escaped[i:i + chunk_size] for i in range(0, len(raw_escaped), chunk_size)]

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Принять все", "callback_data": "approve_all"},
                {"text": "Отклонить", "callback_data": "reject"},
            ],
        ]
    }

    ok = send_message(header + chunks[0], reply_markup=keyboard)
    for chunk in chunks[1:]:
        if ok:
            ok = send_message(f"<pre>{chunk}</pre>")
    return ok


def send_proposals(
    run_id: str,
    proposals: list,
    total_tokens: int = 0,
    cost_rub: float = 0,
    failed_ids: list = None,
) -> bool:
    """
    Отправляет предложения правок в Telegram с inline-кнопками.

    proposals: список dict с ключами file, description, patch (опционально)
    Возвращает True при успехе.
    """
    token, chat_id = _get_token_chat()
    if not token or not chat_id:
        return False

    lines = [
        "<b>Предложения правок</b>",
        f"Run: <code>{run_id}</code>",
    ]
    if failed_ids:
        lines.append(f"Провалившиеся: {', '.join(failed_ids)}")
    if total_tokens or cost_rub:
        lines.append(f"Токены: {total_tokens:,} | Стоимость: ~{cost_rub} ₽")
    lines.append("")
    for i, p in enumerate(proposals, 1):
        desc = p.get("description", "—")[:100]
        f = p.get("file", "?")
        lines.append(f"<b>{i}.</b> {f}")
        lines.append(f"   {desc}")
    lines.append("")
    lines.append("Ответьте свободным текстом: «принять», «отклонить», «1,3» или любой комментарий.")

    text = "\n".join(lines)

    keyboard = {
        "inline_keyboard": [
            [
                {"text": "Принять все", "callback_data": "approve_all"},
                {"text": "Отклонить", "callback_data": "reject"},
            ],
        ]
    }

    return send_message(text, reply_markup=keyboard)


def get_updates(token: str, offset: int = None) -> dict:
    """Получает обновления от Telegram (getUpdates). timeout=25 — long polling."""
    data = {"timeout": 25}
    if offset is not None:
        data["offset"] = offset
    try:
        return _api_request(token, "getUpdates", data)
    except urllib.error.HTTPError as e:
        if e.code == 409:
            _delete_webhook(token)
            raise RuntimeError(
                "getUpdates конфликтует с webhook. Webhook удалён. Запустите скрипт снова."
            ) from e
        raise


def _answer_callback(token: str, callback_query_id: str):
    """Подтверждает нажатие inline-кнопки."""
    try:
        _api_request(token, "answerCallbackQuery", {"callback_query_id": callback_query_id})
    except Exception:
        pass


def _parse_partial_approval(text: str) -> tuple:
    """
    Парсит текст вида "1,3" или "1 3 — комментарий" или "approve 1 3: не менять X".
    Возвращает (indices, comment).
    """
    orig = text.strip()
    text_lower = orig.lower()
    if "approve" in text_lower:
        orig = text_lower.replace("approve", "", 1).strip()
    # Ищем разделитель комментария (— - : или перенос)
    comment = ""
    for sep in (" — ", " - ", ": ", "\n"):
        if sep in orig:
            head, tail = orig.split(sep, 1)
            if tail.strip():
                comment = tail.strip()
            orig = head.strip()
    parts = orig.replace(",", " ").split()
    indices = []
    for i, p in enumerate(parts):
        try:
            n = int(p)
            if 1 <= n <= 100:
                indices.append(n)
        except ValueError:
            # Не число — остаток считаем комментарием
            if not comment:
                comment = " ".join(parts[i:]).strip()
            break
    return sorted(set(indices)), comment


def wait_for_approval(
    timeout_sec: int = 86400,
    poll_interval: int = 5,
) -> tuple:
    """
    Ожидает ответ пользователя в Telegram (callback или текст).

    Возвращает (action, approved_indices, comment):
    - action: "approve_all" | "approve_partial" | "reject" | "timeout"
    - approved_indices: список int (1-based) для approve_partial, или все для approve_all
    - comment: строка комментария пользователя (для approve_partial), иначе ""

    timeout_sec: макс. время ожидания (по умолчанию 24 ч)
    poll_interval: пауза между запросами (с). Long polling 25 с — при нажатии ответ приходит сразу
    """
    token, chat_id = _get_token_chat()
    if not token or not chat_id:
        return "timeout", [], ""

    offset = None
    deadline = time.time() + timeout_sec
    debug = os.environ.get("TELEGRAM_DEBUG", "").strip().lower() in ("1", "true", "yes")

    # Webhook блокирует getUpdates — удаляем при старте
    _delete_webhook(token)

    while time.time() < deadline:
        try:
            resp = get_updates(token, offset)
            if not resp.get("ok"):
                time.sleep(poll_interval)
                continue
            updates = resp.get("result", [])
            if debug and updates:
                print(f"[TG] Получено обновлений: {len(updates)}", flush=True)
            for u in updates:
                offset = u["update_id"] + 1
                # Callback от inline-кнопки
                if "callback_query" in u:
                    cb = u["callback_query"]
                    msg = cb.get("message") or {}
                    chat_id_from = msg.get("chat", {}).get("id") if isinstance(msg, dict) else None
                    if chat_id_from is not None and not _chat_matches(chat_id_from, chat_id):
                        if debug:
                            print(f"[TG] Пропуск callback: chat {chat_id_from} != {chat_id}", flush=True)
                        continue
                    if debug:
                        print(f"[TG] Callback: {cb.get('data')}", flush=True)
                    _answer_callback(token, cb.get("id", ""))
                    data = cb.get("data", "")
                    if data == "approve_all":
                        return "approve_all", [], ""
                    if data == "reject":
                        return "reject", [], ""
                    continue
                # Текстовое сообщение
                if "message" in u:
                    msg = u["message"]
                    if not _chat_matches(msg.get("chat", {}).get("id"), chat_id):
                        if debug:
                            print(f"[TG] Пропуск message: chat != {chat_id}", flush=True)
                        continue
                    text = (msg.get("text") or "").strip()
                    if not text:
                        continue
                    text_lower = text.lower()
                    if text_lower in ("reject", "отклонить", "нет"):
                        return "reject", [], ""
                    if text_lower in ("approve_all", "все", "принять все", "принять", "ок", "ok", "да", "yes"):
                        return "approve_all", [], ""
                    # Парсим "1,3" или "1,3 — комментарий" для частичного одобрения
                    indices, comment = _parse_partial_approval(text)
                    if indices:
                        return "approve_partial", indices, comment
                    # Любой другой текст — одобрить все с комментарием
                    return "approve_all", [], text
        except RuntimeError:
            raise
        except Exception as e:
            if debug:
                print(f"[TG] Ошибка: {e}", flush=True)
        time.sleep(poll_interval)

    return "timeout", [], ""
