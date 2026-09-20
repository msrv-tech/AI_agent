# HTTP-bridge вместо COM

Автотесты, quality gate, RAG и CLI агента ходят в 1С через Codex Test Bridge (`/hs/codex-test`), без `V83.COMConnector`.

## Quality gate

```bash
python automation/bridge/test_examples.py --examples-group extended --score-mode heuristic
python automation/bridge/test_examples.py --bridge-url http://192.168.2.127/fresh-bp-demo/hs/codex-test --user Admin --examples-group smoke
python automation/quality_gate_matrix.py --group extended --score-mode heuristic
```

Переменные `.env`: `BRIDGE_URL`, `BRIDGE_BP_URL`, `BRIDGE_UNF_URL`.

## Модульные тесты ИИА_Тесты

```bash
python automation/ops/run_tests.py --skip-update
python automation/ops/run_bsl_test_bridge.py ТестRunQuery
```

## Диалог агента

```bash
python automation/tau/run_dialog.py --text "Покажи всех контрагентов" --type Запрос1С
```

Серверный вход остаётся в общем модуле `ИИА_ДиалогCOM` — это API автотестов, не Windows COM.
