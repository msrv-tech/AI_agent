# -*- coding: utf-8 -*-
"""
Запуск переиндексации RAG и уведомление в Telegram по окончании.

Вызывает ИИА_RAG_Индексатор.ПерестроитьИндекс() через COM, измеряет время,
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
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from com_1c import connect_to_1c, call_procedure
from com_1c.com_connector import setup_console_encoding
from com_1c.config import get_connection_string

# Загрузка .env для Telegram
try:
    from dotenv import load_dotenv
    _root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    load_dotenv(os.path.join(_root, ".env"))
except ImportError:
    pass


def send_telegram_notification(message: str) -> bool:
    """Отправляет уведомление в Telegram. Возвращает True при успехе."""
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        data = urllib.parse.urlencode({
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/x-www-form-urlencoded")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception:
        return False


def main():
    setup_console_encoding()

    import argparse
    parser = argparse.ArgumentParser(
        description="Переиндексация RAG и уведомление в Telegram"
    )
    parser.add_argument(
        "--connection", "-c",
        default=None,
        help="Строка подключения к 1С",
    )
    parser.add_argument(
        "--no-telegram",
        action="store_true",
        help="Не отправлять уведомление в Telegram",
    )
    args = parser.parse_args()

    connection_string = get_connection_string(args.connection)
    started_at = datetime.now()

    print("Подключение к 1С...")
    conn = connect_to_1c(connection_string)
    if conn is None:
        msg = (
            "<b>RAG: переиндексация — ошибка</b>\n\n"
            "Не удалось подключиться к базе 1С."
        )
        if not args.no_telegram:
            send_telegram_notification(msg)
        return 1

    print("Запуск переиндексации RAG...")
    try:
        call_procedure(conn, "ИИА_RAG_Индексатор", "ПерестроитьИндекс")
    except Exception as exc:
        elapsed = (datetime.now() - started_at).total_seconds()
        err_text = str(exc)
        print(f"Ошибка: {err_text}")
        msg = (
            "<b>RAG: переиндексация — ошибка</b>\n\n"
            f"Время: {elapsed:.1f} с\n"
            f"Ошибка: <code>{err_text[:300]}</code>"
        )
        if not args.no_telegram:
            send_telegram_notification(msg)
        return 1

    elapsed = (datetime.now() - started_at).total_seconds()
    print(f"Переиндексация завершена за {elapsed:.1f} с")

    msg = (
        "<b>RAG: переиндексация завершена</b>\n\n"
        f"Время: {elapsed:.1f} с\n"
        f"Дата: {started_at.strftime('%Y-%m-%d %H:%M')}"
    )
    if not args.no_telegram:
        tg_ok = send_telegram_notification(msg)
        if tg_ok:
            print("Уведомление отправлено в Telegram")
        elif os.environ.get("TELEGRAM_BOT_TOKEN") or os.environ.get("TELEGRAM_CHAT_ID"):
            print("Не удалось отправить уведомление в Telegram")
        else:
            print("Telegram не настроен (TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID в .env)")
    else:
        print("Уведомление в Telegram отключено (--no-telegram)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
