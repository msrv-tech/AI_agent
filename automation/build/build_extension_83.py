# -*- coding: utf-8 -*-
"""
Сборка расширения ИИ_Агент для платформы 8.3.

Создаёт временную базу 8.3, загружает в неё адаптированный XML, выгружает .cfe в bin/.
Не использует основную базу из .env — не требует закрытия сеансов.

Использование:
    python build_extension_83.py

Пути к платформам задаются в .env (PLATFORM_83).
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile

# Поддержка запуска из каталога automation/build
_script_dir = os.path.dirname(os.path.abspath(__file__))
_automation_dir = os.path.dirname(_script_dir)
_repo_root = os.path.dirname(_automation_dir)
for _path in (_script_dir, _automation_dir, _repo_root):
    if _path not in sys.path:
        sys.path.insert(0, _path)

from automation.bridge.config import get_platform_83, setup_console_encoding

EXTENSION_NAME = "ИИ_Агент"

# Версия формата XML: 2.21 — 8.5, 2.14 — 8.3.21 (макс. для 8.3)
XML_VERSION_83 = "2.14"


def copy_and_adapt_xml(src_dir: str, dst_dir: str) -> None:
    """Копирует XML и адаптирует под 8.3."""
    shutil.copytree(src_dir, dst_dir, dirs_exist_ok=False)

    for root, _dirs, files in os.walk(dst_dir):
        for name in files:
            path = os.path.join(root, name)
            lower = name.lower()
            if lower.endswith(".xml"):
                content = _read_utf8(path)
                content = _adapt_xml_content(path, content)
                _write_utf8(path, content)
                continue
            if lower.endswith(".bsl"):
                content = _read_utf8(path)
                # ТекущаяДатаСеанса() добавлена в 8.5, в 8.3 — ТекущаяДата()
                content = content.replace("ТекущаяДатаСеанса()", "ТекущаяДата()")
                _write_utf8(path, content)
                continue


def _read_utf8(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _write_utf8(path: str, content: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def _adapt_xml_content(path: str, content: str) -> str:
    # Версия формата XML
    content = re.sub(r'version="2\.\d+(?:\.\d+)?"', f'version="{XML_VERSION_83}"', content)
    content = re.sub(r'format="[^"]*"\s+version="[^"]*"', f'format="Hierarchical" version="{XML_VERSION_83}"', content)

    # Configuration.xml — режим 8.3.26 и отключение проверки (как в temp/xml83 из конфигуратора)
    # Удаление CompatibilityMode = снятая галочка «Режим совместимости» (не контролировать)
    if "Configuration.xml" in path:
        content = re.sub(
            r"<ConfigurationExtensionCompatibilityMode>Version8_3_\d+</ConfigurationExtensionCompatibilityMode>",
            "<ConfigurationExtensionCompatibilityMode>Version8_3_26</ConfigurationExtensionCompatibilityMode>",
            content,
        )
        content = re.sub(r"\s*<CompatibilityMode>Version8_[^<]*</CompatibilityMode>\s*", "", content)
        content = re.sub(
            r"\s*<InterfaceCompatibilityMode>[^<]*</InterfaceCompatibilityMode>\s*",
            "",
            content,
        )
        content = re.sub(r"\s*<Caption/>\s*", "", content)
        content = re.sub(r"\s*<ShortCaption/>\s*", "", content)

    # Свойства, отсутствующие в 8.3
    content = re.sub(
        r"\s*<UseInInterfaceCompatibilityMode>[^<]*</UseInInterfaceCompatibilityMode>\s*",
        "",
        content,
    )
    content = re.sub(r"\s*<Color>auto</Color>\s*", "", content)
    content = re.sub(
        r"\s*<UseAlternationRowColorBWA>[^<]*</UseAlternationRowColorBWA>\s*",
        "",
        content,
    )

    # WindowOpeningMode: 8.5 — LockOwner/DontBlock, 8.3 — русские значения (Независимый и т.д.)
    content = content.replace("<WindowOpeningMode>LockOwner</WindowOpeningMode>",
                              "<WindowOpeningMode>БлокироватьОкноВладельца</WindowOpeningMode>")
    content = content.replace("<WindowOpeningMode>DontBlock</WindowOpeningMode>",
                              "<WindowOpeningMode>Независимый</WindowOpeningMode>")

    # В режиме 8.3.26 и ниже длина номера строки табличной части должна быть 5
    content = content.replace("<LineNumberLength>9</LineNumberLength>",
                              "<LineNumberLength>5</LineNumberLength>")

    return content


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Сборка расширения для платформы 8.3 в bin/"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Имя выходного файла в bin/ (по умолчанию: ИИ_Агент_8.3.cfe)",
    )
    parser.add_argument(
        "--export-xml",
        action="store_true",
        help="Только создать папку xml83 с адаптированным XML (для ручной загрузки)",
    )
    args = parser.parse_args()
    setup_console_encoding()

    platform_83 = get_platform_83()

    project_root = os.path.dirname(_automation_dir)
    xml_src = os.path.join(project_root, "xml")
    bin_dir = os.path.join(project_root, "bin")
    output_name = args.output or f"{EXTENSION_NAME}_8.3.cfe"
    cfe_path = os.path.join(bin_dir, output_name)

    if not os.path.isdir(xml_src):
        print(f"Ошибка: каталог xml не найден: {xml_src}", file=sys.stderr)
        sys.exit(1)

    xml83_dir = os.path.join(project_root, "xml83")
    if args.export_xml:
        if os.path.isdir(xml83_dir):
            shutil.rmtree(xml83_dir, ignore_errors=True)
        copy_and_adapt_xml(xml_src, xml83_dir)
        print(f"Готово: {xml83_dir}")
        return

    if not os.path.isfile(platform_83):
        print(f"Ошибка: 1cv8 не найден: {platform_83}", file=sys.stderr)
        sys.exit(1)

    platform_bin = os.path.dirname(os.path.abspath(platform_83))
    log_dir = os.path.join(_script_dir, "logs")
    os.makedirs(log_dir, exist_ok=True)
    load_log = os.path.join(log_dir, "build_83_load.log")
    dump_log = os.path.join(log_dir, "build_83_dump.log")

    temp_dir = None
    temp_db_path = None
    build_ok = False
    try:
        # Путь в проекте — системный temp может иметь 8.3-короткий путь, несовместимый с 1С
        temp_dir = os.path.join(project_root, "temp_build_83")
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)
        os.makedirs(temp_dir, exist_ok=True)
        xml_temp = os.path.join(temp_dir, "xml")
        temp_db_path = os.path.join(temp_dir, "db")
        print(f"Временный каталог: {temp_dir}")
        copy_and_adapt_xml(xml_src, xml_temp)
        print("XML адаптированы под 8.3 (version=2.14, CompatibilityMode=8.3.26)")

        def run_1cv8(arg_list: list, op_name: str) -> int:
            print(f"==> {op_name}")
            print("    1cv8.exe", " ".join(arg_list))
            result = subprocess.run(
                [platform_83] + arg_list,
                capture_output=False,
                timeout=600,
                cwd=platform_bin,
            )
            if result.returncode != 0:
                print(f"Ошибка: 1cv8 завершился с кодом {result.returncode}", file=sys.stderr)
            return result.returncode

        # Создаём временную базу 8.3
        abs_db = os.path.abspath(temp_db_path)
        create_cmd_str = f'"{platform_83}" CREATEINFOBASE File="{abs_db}"'
        print("==> Создание временной базы 8.3")
        create_result = subprocess.run(
            create_cmd_str,
            capture_output=True,
            timeout=60,
            cwd=platform_bin,
            shell=True,
        )
        if create_result.returncode != 0:
            for stream, name in [(create_result.stderr, "stderr"), (create_result.stdout, "stdout")]:
                if stream:
                    try:
                        text = stream.decode("cp1251", errors="replace")
                    except Exception:
                        text = stream.decode("utf-8", errors="replace")
                    if text.strip():
                        print(f"[{name}]", text.strip(), file=sys.stderr)
            print(f"Ошибка: CreateINFOBASE завершился с кодом {create_result.returncode}", file=sys.stderr)
            sys.exit(1)

        base_args = [
            "DESIGNER",
            "/DisableStartupDialogs",
            "/DisableStartupMessages",
            "/F", temp_db_path,
        ]

        load_args = base_args + [
            "/Out", load_log,
            "/LoadConfigFromFiles", os.path.abspath(xml_temp),
            "-Extension", EXTENSION_NAME,
        ]
        if run_1cv8(load_args, "Загрузка XML 8.3 в конфигурацию") != 0:
            sys.exit(1)

        os.makedirs(bin_dir, exist_ok=True)
        cfe_full = os.path.abspath(cfe_path)
        dump_args = base_args + [
            "/Out", dump_log,
            "/DumpCfg", cfe_full,
            "-Extension", EXTENSION_NAME,
        ]
        if run_1cv8(dump_args, "Выгрузка в .cfe") != 0:
            sys.exit(1)

        print(f"Готово: {cfe_path}")
        build_ok = True

    except subprocess.TimeoutExpired:
        print("Ошибка: превышено время ожидания", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Ошибка: {e}", file=sys.stderr)
        raise
    finally:
        if temp_dir and os.path.isdir(temp_dir):
            if build_ok:
                shutil.rmtree(temp_dir, ignore_errors=True)
                print("Временные файлы удалены.")
            else:
                print(f"Временные файлы сохранены для отладки: {temp_dir}")


if __name__ == "__main__":
    main()
