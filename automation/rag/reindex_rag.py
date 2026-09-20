# -*- coding: utf-8 -*-
"""
Запуск переиндексации RAG и уведомление в Telegram по окончании.

Вызывает ИИА_RAG_Индексатор.ПерестроитьИндекс() через HTTP-bridge, измеряет время,
отправляет уведомление в Telegram (успех или ошибка).

Запуск (из каталога automation):
    python reindex_rag.py
    python reindex_rag.py --connection "File=\"D:\\base\";"

Секреты Telegram в .env: TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""

import sys
import os
import urllib.request
import urllib.error
import urllib.parse
from datetime import datetime

_script_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_script_dir)
_repo_root = os.path.dirname(_automation_dir)
for _path in (_script_dir, _automation_dir, _repo_root):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from automation.bridge.client import call_exported
from automation.bridge.config import get_bridge_url, setup_console_encoding

# Загрузка .env для Telegram
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass

DEFAULT_TELEGRAM_PROXY_URL = "http://192.168.2.124:10808"


def send_telegram_notification(message: str) -> bool:
    """Отправляет уведомление в Telegram. Возвращает True при успехе."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        proxy_url = os.environ.get("TELEGRAM_PROXY_URL") or DEFAULT_TELEGRAM_PROXY_URL
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({"http": proxy_url, "https": proxy_url})
        ) if proxy_url else urllib.request.build_opener()
        with opener.open(req, timeout=20) as resp:
            return resp.status == 200
    except Exception:
        return False


def send_telegram_with_status(message: str, disabled: bool = False) -> None:
    """Отправляет уведомление и печатает понятный статус в консоль."""
    if disabled:
        print("Уведомление в Telegram отключено (--no-telegram)")
        return

    tg_ok = send_telegram_notification(message)
    if tg_ok:
        print("Уведомление отправлено в Telegram")
    elif os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_CHAT_ID"):
        print("Не удалось отправить уведомление в Telegram")
    else:
        print("Telegram не настроен (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID в .env)")


def main():
    setup_console_encoding()

    import argparse
    parser = argparse.ArgumentParser(
        description="Переиндексация RAG и уведомление в Telegram"
    )
    parser.add_argument(
        "--bridge-url",
        default=None,
        help="URL HTTP-сервиса Codex Test Bridge",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Не отправлять уведомление в Telegram",
    )
    args = parser.parse_args()

    started_at = datetime.now()

    print("Запуск переиндексации RAG...")
    try:
        call_exported(get_bridge_url(args.bridge_url), "ИИА_RAG_Индексатор", "ПерестроитьИндекс", timeout=600)
    except Exception as exc:
        elapsed = (datetime.now() - started_at).total_seconds()
        err_text = str(exc)
        print(f"Ошибка: {err_text}")
        msg = (
            "<b>RAG: переиндексация — ошибка</b>\n\n"
            f"Время: {elapsed:.1f} с\n"
            f"Ошибка: <code>{err_text[:300]}</code>"
        )
        send_telegram_with_status(msg, args.no_telegram)
        return 1

    elapsed = (datetime.now() - started_at).total_seconds()
    print(f"Переиндексация завершена за {elapsed:.1f} с")

    msg = (
        "<b>RAG: переиндексация завершена</b>\n\n"
        f"Время: {elapsed:.1f} с\n"
        f"Дата: {started_at.strftime('%Y-%m-%d %H:%M')}"
    )
    send_telegram_with_status(msg, args.no_telegram)

    return 0


if __name__ == "__main__":
    sys.exit(main())
