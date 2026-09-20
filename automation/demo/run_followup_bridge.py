# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
AUTOMATION = ROOT / "automation"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(AUTOMATION))

from automation.bridge.client import bsl_string, execute_bsl
from automation.bridge.config import get_bridge_url


def _as_bool(value) -> bool:
    try:
        return bool(value)
    except Exception:
        return False


def _as_int(value) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return 0


def _field(obj, name, default=None):
    if isinstance(obj, dict):
        return obj.get(name, default)
    return default


def run_scenario(bridge_url: str, scenario: dict, out_dir: Path) -> dict:
    result = {
        "id": scenario["id"],
        "title": scenario["title"],
        "success": False,
        "turns": [],
        "query": "",
        "rows": 0,
        "usage_tokens": 0,
        "errors": [],
    }

    session = execute_bsl(
        bridge_url,
        "РезультатВыполнения = ИИА_ДиалогCOM.СоздатьBridgeСессию("
        + bsl_string("Администратор")
        + ", Перечисления.ИИА_ТипДиалога.Запрос1С);",
    )
    session_id = str(_field(session, "SessionId") or "")
    messages = [scenario["prompt"]] + list(scenario.get("followups", []))
    last = None
    for index, text in enumerate(messages, start=1):
        turn = execute_bsl(
            bridge_url,
            "РезультатВыполнения = ИИА_ДиалогCOM.ВыполнитьХодBridge("
            + bsl_string(session_id)
            + ", "
            + bsl_string(text)
            + ");",
            timeout=280,
        )
        last = turn
        turn_success = _as_bool(_field(turn, "Успех"))
        usage = _as_int(_field(turn, "UsageTokens"))
        result["turns"].append({"index": index, "text": text, "success": turn_success, "usage_tokens": usage})
        result["usage_tokens"] = usage
        if not turn_success:
            result["errors"].append(f"turn {index} failed")
            break

    if last is not None:
        dialog_uuid = session_id
        state = execute_bsl(
            bridge_url,
            "СсылкаДиалога = Справочники.ИИА_Диалоги.ПолучитьСсылку(Новый УникальныйИдентификатор("
            + bsl_string(dialog_uuid)
            + ")); РезультатВыполнения = ИИА_Сервер.ПолучитьСостояниеЗапроса1С(СсылкаДиалога);",
        )
        result["query"] = str(_field(state, "ТекстЗапроса") or "")
        result["rows"] = _as_int(_field(state, "КоличествоСтрок"))
        log_text = str(_field(last, "Лог") or "")
        (out_dir / f"{scenario['id']}.log").write_text(log_text, encoding="utf-8")
        (out_dir / f"{scenario['id']}.query.txt").write_text(result["query"], encoding="utf-8")

    query_lower = result["query"].lower()
    for needle in scenario.get("expected_query_contains", []):
        if str(needle).lower() not in query_lower:
            result["errors"].append(f"query does not contain {needle!r}")
    if result["rows"] < int(scenario.get("min_rows", 0)):
        result["errors"].append(f"rows {result['rows']} < {scenario.get('min_rows')}")
    result["success"] = not result["errors"] and all(t["success"] for t in result["turns"])
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenarios", default=str(Path(__file__).with_name("followup_scenarios.json")))
    parser.add_argument("--bridge-url", default=None)
    parser.add_argument("--only", nargs="*", default=None)
    args = parser.parse_args()

    scenarios = json.loads(Path(args.scenarios).read_text(encoding="utf-8"))
    if args.only:
        wanted = set(args.only)
        scenarios = [item for item in scenarios if item["id"] in wanted]

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = ROOT / "automation" / "logs" / "demo_followups" / f"bridge_{stamp}"
    out_dir.mkdir(parents=True, exist_ok=True)
    bridge_url = get_bridge_url(args.bridge_url)

    results = []
    for scenario in scenarios:
        print(f"\n== {scenario['id']} ==")
        res = run_scenario(bridge_url, scenario, out_dir)
        results.append(res)
        print(f"success={res['success']} rows={res['rows']} usage={res['usage_tokens']}")
        if res["errors"]:
            print("errors:", "; ".join(res["errors"]))
        print(res["query"][:500])

    report = {"out_dir": str(out_dir), "results": results}
    (out_dir / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    ok_ids = [item["id"] for item in results if item["success"]]
    (out_dir / "successful_ids.txt").write_text("\n".join(ok_ids), encoding="utf-8")
    print(f"\nReport: {out_dir / 'report.json'}")
    print("Successful:", ", ".join(ok_ids))
    return 0 if ok_ids else 1


if __name__ == "__main__":
    raise SystemExit(main())
