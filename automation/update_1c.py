# -*- coding: utf-8 -*-
"""
Сборка расширения из XML, загрузка в конфигурацию, обновление БД и запуск 1С.

Использует тот же .env, что run_dialog.py и COM (1C_CONNECTION_STRING).

Примеры:
    python update_1c.py
        Полный цикл: xml -> .cfe -> загрузка -> обновление БД -> запуск 1С

    python update_1c.py --skip-run-client
        Сборка и обновление без запуска 1С

    python update_1c.py --no-build-from-xml
        Без сборки: только загрузка .cfe и обновление БД

    python update_1c.py --skip-load-extension
        Только обновление БД (расширение уже загружено)
"""

import argparse
import os
import subprocess
import sys

# Поддержка запуска из каталога automation
_script_dir = os.path.dirname(os.path.abspath(__file__))
if _script_dir not in sys.path:
    sys.path.insert(0, _script_dir)

from com_1c.config import get_connection_string
from com_1c.com_connector import setup_console_encoding

EXTENSION_NAME = "ИИ_Агент"
DEFAULT_PLATFORM = r"C:\Program Files\1cv8\8.5.1.1150\bin\1cv8.exe"


def main():
    parser = argparse.ArgumentParser(
        description="Сборка расширения из XML, загрузка, обновление БД, запуск 1С"
    )
    parser.add_argument(
        "--no-build-from-xml",
        dest="build_from_xml",
        action="store_false",
        help="Пропустить сборку из xml (по умолчанию: собирать)",
    )
    parser.add_argument(
        "--skip-load-extension",
        action="store_true",
        help="Не загружать .cfe (только обновить БД)",
    )
    parser.add_argument(
        "--skip-db-update",
        action="store_true",
        help="Не обновлять конфигурацию БД",
    )
    parser.add_argument(
        "--skip-run-client",
        action="store_true",
        help="Не запускать 1С:Предприятие",
    )
    args = parser.parse_args()
    setup_console_encoding()

    project_root = os.path.dirname(_script_dir)
    log_dir = os.path.join(_script_dir, "logs")
    xml_path = os.path.join(project_root, "xml")
    cfe_path = os.path.join(project_root, "bin", f"{EXTENSION_NAME}.cfe")

    connection_string = get_connection_string()
    os.environ["1C_CONNECTION_STRING"] = connection_string
    print(f"База: {connection_string[:70]}...")

    platform_exe = DEFAULT_PLATFORM
    if not os.path.isfile(platform_exe):
        print(f"Ошибка: 1cv8 не найден: {platform_exe}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(log_dir, exist_ok=True)

    cfe_full = os.path.abspath(cfe_path)
    if not args.skip_load_extension and not args.build_from_xml:
        if not os.path.isfile(cfe_full):
            print(f"Ошибка: .cfe не найден: {cfe_full}", file=sys.stderr)
            sys.exit(1)

    if args.build_from_xml:
        if not os.path.isdir(xml_path):
            print(f"Ошибка: каталог xml не найден: {xml_path}", file=sys.stderr)
            sys.exit(1)

    platform_bin = os.path.dirname(os.path.abspath(platform_exe))

    def run_1cv8(arg_list: list, op_name: str, wait: bool = True) -> int:
        print(f"==> {op_name}")
        print("    1cv8.exe", " ".join(arg_list))
        result = subprocess.run(
            [platform_exe] + arg_list,
            capture_output=False,
            timeout=600,
            cwd=platform_bin,
        )
        if wait and result.returncode != 0:
            print(f"Ошибка: 1cv8 завершился с кодом {result.returncode}", file=sys.stderr)
        return result.returncode

    base_args = [
        "DESIGNER",
        "/DisableStartupDialogs",
        "/DisableStartupMessages",
        "/IBConnectionString", connection_string,
    ]

    update_log = os.path.abspath(os.path.join(log_dir, "update-db.log"))
    build_load_log = os.path.abspath(os.path.join(log_dir, "build-load.log"))
    build_dump_log = os.path.abspath(os.path.join(log_dir, "build-dump.log"))

    done = []

    try:
        if args.build_from_xml:
            os.makedirs(os.path.dirname(cfe_full), exist_ok=True)
            xml_full = os.path.abspath(xml_path)

            load_args = base_args + [
                "/Out", build_load_log,
                "/LoadConfigFromFiles", xml_full,
                "-Extension", EXTENSION_NAME,
            ]
            if run_1cv8(load_args, "Загрузка xml в конфигурацию") != 0:
                sys.exit(1)
            done.append("собрано из xml")

            dump_args = base_args + [
                "/Out", build_dump_log,
                "/DumpCfg", cfe_full,
                "-Extension", EXTENSION_NAME,
            ]
            if run_1cv8(dump_args, "Выгрузка в .cfe") != 0:
                sys.exit(1)

        need_load = not args.skip_load_extension
        need_update = not args.skip_db_update

        if need_load or need_update:
            base_args.extend(["/Out", update_log])

            if need_load:
                load_cfg_args = base_args + [
                    "/LoadCfg", cfe_full,
                    "-Extension", EXTENSION_NAME,
                ]
                if run_1cv8(load_cfg_args, "Загрузка .cfe в конфигурацию") != 0:
                    sys.exit(1)
                done.append("загружено")

            if need_update:
                update_args = base_args + [
                    "/UpdateDBCfg",
                    "-Extension", EXTENSION_NAME,
                ]
                if run_1cv8(update_args, "Обновление конфигурации БД") != 0:
                    sys.exit(1)
                done.append("БД обновлена")

        if not args.skip_run_client:
            ent_args = [
                "ENTERPRISE",
                "/DisableStartupDialogs",
                "/DisableStartupMessages",
                "/IBConnectionString", connection_string,
            ]
            proc = subprocess.Popen(
                [platform_exe] + ent_args,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                cwd=platform_bin,
            )
            print("==> Запуск 1С:Предприятие (PID %d)" % proc.pid)
            done.append("клиент запущен")
        else:
            print("Запуск клиента пропущен.")

        print("Готово:", ", ".join(done) if done else "—")

    except subprocess.TimeoutExpired:
        print("Ошибка: превышено время ожидания", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
