# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "automation"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(AUTOMATION))

from automation.bridge.client import query
from automation.bridge.config import get_bridge_url


PROBES = {
    "Контрагенты всего / покупатели / с ИНН": [
        ("Всего", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ Справочник.Контрагенты КАК К'),
        ("Покупатели", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ Справочник.Контрагенты КАК К ГДЕ К.Покупатель = ИСТИНА'),
        ("С ИНН", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ Справочник.Контрагенты КАК К ГДЕ НЕ К.ИНН = ""'),
    ],
    "Номенклатура / стол": [
        ("Всего", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ Справочник.Номенклатура КАК Н'),
        ("Содержит стол", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ Справочник.Номенклатура КАК Н ГДЕ Н.Наименование ПОДОБНО "%стол%"'),
    ],
    "Продажи и реализации": [
        ("Продажи апрель 2022", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ РегистрНакопления.Продажи КАК П ГДЕ П.Период >= ДАТАВРЕМЯ(2022, 4, 1) И П.Период < ДАТАВРЕМЯ(2022, 5, 1)'),
        ("Реализации апрель 2022", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ Документ.РасходнаяНакладная КАК Д ГДЕ Д.Дата >= ДАТАВРЕМЯ(2022, 4, 1) И Д.Дата < ДАТАВРЕМЯ(2022, 5, 1)'),
    ],
    "Остатки": [
        ("Розничный магазин", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ РегистрНакопления.ЗапасыНаСкладах.Остатки КАК З ГДЕ З.СтруктурнаяЕдиница.Наименование = "Розничный магазин" И З.КоличествоОстаток <> 0'),
        ("Остаток 1", 'ВЫБРАТЬ КОЛИЧЕСТВО(*) КАК C ИЗ РегистрНакопления.ЗапасыНаСкладах.Остатки КАК З ГДЕ З.КоличествоОстаток = 1'),
    ],
}


def _count(payload: dict) -> int:
    rows = payload.get("rows") or payload.get("result") or []
    if isinstance(rows, list) and rows:
        first = rows[0]
        if isinstance(first, dict):
            value = first.get("C") or first.get("c") or next(iter(first.values()), 0)
            return int(float(str(value).replace(",", ".")))
    count = payload.get("count")
    if count is not None:
        return int(count)
    return 0


def main() -> int:
    bridge_url = get_bridge_url()
    result = {}
    for group, checks in PROBES.items():
        result[group] = {}
        print(f"\n## {group}")
        for name, text in checks:
            try:
                payload = query(bridge_url, text, limit=1)
                count = _count(payload)
                result[group][name] = count
                print(f"{name}: {count}")
            except Exception as exc:
                result[group][name] = f"ERROR: {exc}"
                print(f"{name}: ERROR {exc}")
    out_dir = ROOT / "automation" / "logs" / "demo_followups"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "data_probe.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
