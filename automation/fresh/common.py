# -*- coding: utf-8 -*-
"""Pure helpers for Fresh CFE naming, version and release notes."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path


VERSION_RE = re.compile(r"<Version>([^<]+)</Version>")
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_XML = PROJECT_ROOT / "xml" / "Configuration.xml"
DEFAULT_RELEASES_DIR = PROJECT_ROOT / "docs" / "releases"


def read_extension_version(config_xml: Path = DEFAULT_CONFIG_XML) -> str:
    if not config_xml.is_file():
        raise RuntimeError(f"Нет Configuration.xml: {config_xml}")
    match = VERSION_RE.search(config_xml.read_text(encoding="utf-8-sig"))
    if match is None:
        raise RuntimeError(f"В {config_xml} нет <Version>")
    version = match.group(1).strip()
    if not version:
        raise RuntimeError(f"Пустая <Version> в {config_xml}")
    return version


def fresh_cfe_name(version: str) -> str:
    if not version:
        raise RuntimeError("Пустая версия расширения")
    return f"AI_Agent_Fresh_{version}.cfe"


def changelog_from_release_notes(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Нет release notes: {path}")
    bullets: list[str] = []
    in_main = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            if in_main:
                break
            in_main = stripped == "## Главное"
            continue
        if in_main and stripped.startswith("- "):
            bullets.append(stripped[2:].strip())
    if not bullets:
        raise RuntimeError(f"В {path} нет пунктов секции «Главное»")
    return "\n".join(f"- {item}" for item in bullets)


def changelog_for_version(version: str, releases_dir: Path = DEFAULT_RELEASES_DIR) -> str:
    return changelog_from_release_notes(releases_dir / f"v{version}.md")


def file_sha256(path: Path) -> str:
    if not path.is_file():
        raise RuntimeError(f"Файл не найден: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def env_flag(name: str) -> str:
    return (os.getenv(name) or "").strip()
