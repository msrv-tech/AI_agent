# -*- coding: utf-8 -*-
"""Собрать Fresh-редакцию текущей версии и загрузить её в 1С:Фреш.

По умолчанию:
  1. читает <Version> из xml/Configuration.xml;
  2. готовит Fresh XML и собирает CFE во временной файловой ИБ;
  3. открывает Менеджер сервиса и загружает новую версию расширения «ИИ агент».

Аудит/автопроверка запускаются только при завершении мастера.
Установка в приложение и отправка на ручной аудит не делаются.

Примеры:
  python3 automation/ops/deploy_fresh.py --build-only --platform /opt/1cv8/x86_64/8.5.1.1150/1cv8
  python3 automation/ops/deploy_fresh.py --platform /opt/1cv8/x86_64/8.5.1.1150/1cv8
  python3 automation/ops/deploy_fresh.py --no-build --cfe bin/AI_Agent_Fresh_0.9.9.cfe --draft
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from automation.build.build_extension_fresh import (  # noqa: E402
    DEFAULT_PREPARED,
    DEFAULT_SOURCE,
    build_cfe,
    build_cfe_temp_ib,
    load_extension_xml,
    prepare_source,
    resolve_platform,
)
from automation.fresh.common import (  # noqa: E402
    changelog_for_version,
    env_flag,
    file_sha256,
    fresh_cfe_name,
    read_extension_version,
)
from automation.fresh.upload import DEFAULT_ADM_URL, DEFAULT_EXTENSION_TITLE, upload_fresh_version  # noqa: E402


def load_env_file(path: Path) -> None:
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key or key in os.environ:
            continue
        os.environ[key] = value.strip().strip('"').strip("'")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Сборка и деплой Fresh-редакции в Менеджер сервиса 1С:Фреш")
    parser.add_argument("--platform", default=env_flag("PLATFORM_85"))
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--prepared", type=Path, default=DEFAULT_PREPARED)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--cfe", type=Path, default=None, help="Уже собранный CFE, если --no-build")
    parser.add_argument("--build-only", action="store_true", help="Только подготовить XML и собрать CFE")
    parser.add_argument("--no-build", action="store_true", help="Не собирать, загрузить существующий CFE")
    parser.add_argument("--draft", action="store_true", help="Остановить мастер до «Завершить»")
    parser.add_argument("--headed", action="store_true")
    parser.add_argument("--adm-url", default=env_flag("FRESH_ADM_URL") or DEFAULT_ADM_URL)
    parser.add_argument("--extension-title", default=env_flag("FRESH_EXTENSION_TITLE") or DEFAULT_EXTENSION_TITLE)
    parser.add_argument("--user", default=env_flag("FRESH_CLOUD_USER"))
    parser.add_argument("--password", default=env_flag("FRESH_CLOUD_PASSWORD"))
    parser.add_argument("--auth-state", default=env_flag("FRESH_AUTH_STATE"))
    parser.add_argument("--server", default=env_flag("FRESH_1C_SERVER"))
    parser.add_argument("--ref", default=env_flag("FRESH_1C_REF"))
    parser.add_argument("--ib-user", default=env_flag("FRESH_1C_USER"))
    parser.add_argument("--ib-password", default=env_flag("FRESH_1C_PASSWORD"))
    parser.add_argument("--connection-string", default=env_flag("FRESH_1C_CONNECTION_STRING"))
    parser.add_argument("--timeout-sec", type=int, default=180)
    parser.add_argument("--artifact-dir", type=Path, default=REPO_ROOT / "automation" / "logs" / "fresh_deploy")
    parser.add_argument(
        "--temp-ib",
        action="store_true",
        help="Собрать CFE во временной файловой ИБ. Нужна локальная лицензия 1С.",
    )
    parser.add_argument(
        "--keep-fresh-ib",
        action="store_true",
        help="Не возвращать в сборочную ИБ обычные xml/ после выгрузки Fresh CFE.",
    )
    return parser.parse_args()


def build_current_cfe(args: argparse.Namespace, version: str) -> Path:
    output = args.output or (REPO_ROOT / "bin" / fresh_cfe_name(version))
    prepare_source(args.source.resolve(), args.prepared.resolve())
    platform = resolve_platform(Path(args.platform))
    use_existing_ib = bool((args.server and args.ref) or args.connection_string)
    if args.temp_ib and use_existing_ib:
        raise RuntimeError("Нельзя одновременно --temp-ib и параметры существующей ИБ.")
    if args.temp_ib:
        build_cfe_temp_ib(args.prepared.resolve(), output.resolve(), platform)
    elif use_existing_ib:
        build_cfe(
            args.prepared.resolve(),
            output.resolve(),
            args.connection_string,
            args.server,
            args.ref,
            args.ib_user,
            args.ib_password,
            platform,
        )
        if not args.keep_fresh_ib:
            load_extension_xml(
                args.source.resolve(),
                platform,
                args.connection_string,
                args.server,
                args.ref,
                args.ib_user,
                args.ib_password,
            )
    else:
        raise RuntimeError(
            "Для сборки CFE нужна лицензированная ИБ: задайте FRESH_1C_SERVER/FRESH_1C_REF "
            "или --temp-ib (файловая ИБ, нужна локальная лицензия 1С)."
        )
    return output.resolve()


def main() -> int:
    load_env_file(REPO_ROOT / ".env")
    args = parse_args()
    if args.build_only and args.no_build:
        raise RuntimeError("Нельзя одновременно --build-only и --no-build.")
    version = read_extension_version(args.source / "Configuration.xml")
    changelog = changelog_for_version(version)
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    artifact_dir = args.artifact_dir / f"deploy_{timestamp}"
    artifact_dir.mkdir(parents=True, exist_ok=True)

    if args.no_build:
        cfe_path = (args.cfe or args.output or (REPO_ROOT / "bin" / fresh_cfe_name(version))).resolve()
        if not cfe_path.is_file():
            raise RuntimeError(f"CFE не найден: {cfe_path}")
    else:
        cfe_path = build_current_cfe(args, version)

    report = {
        "version": version,
        "cfe": str(cfe_path),
        "sha256": file_sha256(cfe_path),
        "changelog": changelog,
        "artifact_dir": str(artifact_dir),
        "uploaded": False,
        "finished": False,
    }
    print(json.dumps({k: report[k] for k in ("version", "cfe", "sha256")}, ensure_ascii=False, indent=2), flush=True)

    if args.build_only:
        (artifact_dir / "deploy_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Собран Fresh CFE: {cfe_path}")
        return 0

    auth_state = Path(args.auth_state) if args.auth_state else None
    upload_report = upload_fresh_version(
        cfe_path=cfe_path,
        version=version,
        changelog=changelog,
        adm_url=args.adm_url,
        extension_title=args.extension_title,
        user=args.user,
        password=args.password,
        artifact_dir=artifact_dir,
        headed=args.headed,
        finish=not args.draft,
        auth_state=auth_state,
        timeout_sec=args.timeout_sec,
    )
    report["uploaded"] = True
    report["finished"] = bool(upload_report.get("finished"))
    report["upload"] = upload_report
    (artifact_dir / "deploy_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"uploaded": True, "finished": report["finished"], "report": str(artifact_dir / "deploy_report.json")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
