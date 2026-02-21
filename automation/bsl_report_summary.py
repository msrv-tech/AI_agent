#!/usr/bin/env python3
"""
Извлекает из bsl-json.json краткий отчёт: файл, строка, серьёзность, код, сообщение.
"""
import json
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

SEVERITY_ORDER = {"Error": 1, "Warning": 2, "Information": 3, "Hint": 4}
SEVERITY_LABEL = {"Error": "Ошибка", "Warning": "Замечание", "Information": "Информация", "Hint": "Подсказка"}
SUMMARY_FILENAME = "bsl-summary.txt"


def short_path(uri: str) -> str:
    """Сокращает file:///path/.../xml/.../Module.bsl до xml/.../Module.bsl"""
    if uri.startswith("file:///"):
        p = Path(unquote(urlparse(uri).path))
        parts = p.parts
        for i, part in enumerate(parts):
            if part == "xml" and i + 1 < len(parts):
                return "/".join(parts[i:])
    return uri


def main():
    script_dir = Path(__file__).resolve().parent
    logs_dir = script_dir / "logs"
    json_path = logs_dir / "bsl-json.json"

    if not json_path.exists():
        print(f"Ошибка: {json_path} не найден. Запустите анализ с --reporter json.", file=sys.stderr)
        sys.exit(1)

    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    lines = [
        f"BSL-анализ: {data.get('date', '?')}",
        "",
    ]

    counts = {"Error": 0, "Warning": 0, "Information": 0, "Hint": 0}
    for fileinfo in data.get("fileinfos", []):
        path = fileinfo.get("path", "")
        mdo_ref = fileinfo.get("mdoRef", "")
        diags = fileinfo.get("diagnostics", [])

        if not diags:
            continue

        relevant = [d for d in diags if d.get("severity") not in ("Information", "Hint")]
        if not relevant:
            continue
        short = short_path(path)
        lines.append(f"── {short} ({mdo_ref})")
        for d in sorted(relevant, key=lambda x: (SEVERITY_ORDER.get(x.get("severity", "Hint"), 5), x.get("range", {}).get("start", {}).get("line", 0))):
            sev = d.get("severity", "Hint")
            code = d.get("code", "?")
            msg = d.get("message", "")
            sev_ru = SEVERITY_LABEL.get(sev, sev)
            r = d.get("range", {}).get("start", {})
            line = r.get("line", 0) + 1
            col = r.get("character", 0) + 1
            lines.append(f"   {line}:{col}  [{sev_ru}] {code}: {msg}")
            counts[sev] = counts.get(sev, 0) + 1
        lines.append("")

    total = sum(counts.values())
    lines.append("─" * 50)
    for sev in ("Error", "Warning",):
        if counts.get(sev):
            lines.append(f"{SEVERITY_LABEL[sev]}: {counts[sev]}")
    lines.append(f"Всего: {total}")

    out_path = logs_dir / SUMMARY_FILENAME
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(out_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
