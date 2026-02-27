# -*- coding: utf-8 -*-
"""
Проверка: может ли Cursor Agent создать файл.
Задача: создать test_agent_output.txt с текстом "test"
"""

import os
import sys
import subprocess
import shutil

_script_dir = os.path.dirname(os.path.abspath(__file__))
_root = os.path.dirname(_script_dir)
OUTPUT_FILE = os.path.join(_root, "test_agent_output.txt")


def _find_agent():
    local = os.environ.get("LOCALAPPDATA", "")
    agent_path = shutil.which("agent")
    if not agent_path:
        for name in ("agent.exe", "agent.cmd", "cursor-agent.exe"):
            p = os.path.join(local, "cursor-agent", name)
            if os.path.isfile(p):
                agent_path = p
                break
    cursor_cmd = os.path.join(local, "Programs", "cursor", "resources", "app", "bin", "cursor.cmd")
    cursor_path = shutil.which("cursor") or (cursor_cmd if os.path.isfile(cursor_cmd) else None)
    if agent_path:
        return agent_path, "agent"
    if cursor_path:
        return cursor_path, "cursor_agent"
    return None, None


def main():
    agent_path, kind = _find_agent()
    if not agent_path:
        print("Agent не найден.")
        return 1

    if os.path.isfile(OUTPUT_FILE):
        os.remove(OUTPUT_FILE)
        print(f"Удалён старый {OUTPUT_FILE}")

    prompt = f"""Создай файл test_agent_output.txt в корне workspace ({_root}) с одной строкой: test
Используй инструмент записи файлов, не terminal."""
    print(f"Промпт: {prompt[:80]}...")
    print(f"Агент: {agent_path} ({kind})")
    print("Запуск (timeout 5 мин, вывод агента в реальном времени)...")
    print("-" * 50)

    base = ["--trust", "-f", "--workspace", _root, "-p", prompt, "--mode", "agent"]
    if kind == "agent":
        cmd = [agent_path] + base
    else:
        cmd = [agent_path, "agent"] + base

    try:
        r = subprocess.run(
            cmd,
            cwd=_root,
            timeout=300,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        print("-" * 50)
        print(f"returncode: {r.returncode}")
    except subprocess.TimeoutExpired:
        print("-" * 50)
        print("TIMEOUT 5 мин")
        return 1
    except Exception as e:
        print(f"Ошибка: {e}")
        return 1

    if os.path.isfile(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            content = f.read()
        print(f"OK: файл создан: {OUTPUT_FILE}")
        print(f"Содержимое: {repr(content)}")
        return 0
    else:
        print(f"Файл НЕ создан: {OUTPUT_FILE}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
