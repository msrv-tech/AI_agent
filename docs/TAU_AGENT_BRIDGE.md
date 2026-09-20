# Tau Agent Bridge

Этот документ описывает bridge-слой для запуска именно вашего 1С-агента внутри внешнего benchmark-контура.

## Что уже сделано

В репозитории добавлен scaffold и runtime:

- [`tau_bridge.py`](../automation/tau/tau_bridge.py) — CLI bridge между benchmark runner и HTTP-входом 1С-агента;
- [`tau_bridge_config.example.json`](../automation/tau/tau_bridge_config.example.json) — шаблон конфига;
- [`tau2_1c_agent.py`](../automation/tau/tau2_1c_agent.py) — custom agent для Tau-Bench;
- [`run_tau_with_1c_agent.py`](../automation/tau/run_tau_with_1c_agent.py) — programmatic runner;
- [`run_tau_bench.py`](../automation/tau/run_tau_bench.py) — внешний запуск официального Tau-Bench как отдельного benchmark-контура.

## Текущий режим scaffold

Bridge поддерживает два режима:

- `stateless replay`
- `session mode`

В `session mode` используются HTTP-bridge entrypoints:

- `СоздатьBridgeСессию`
- `ВыполнитьХодBridge`
- `ЗакрытьBridgeСессию`

Это уже рабочая точка интеграции для реального turn-by-turn прогона.

## Почему начинаем так

- У вас уже есть стабильный HTTP-bridge entrypoint.
- Можно начать с минимального количества новых рисков.
- Ошибки будут локализованы в bridge-слое, а не размазаны по 1С-ядру и внешнему benchmark.

## Ограничения текущего scaffold

- Сессия фактически stateless: каждое обращение replay-ит историю в новом диалоге.
- Нет прямого маппинга tool-calls Tau-Bench на внутренние действия 1С.
- Нет отдельного judge слоя, который валидирует результат задачи по контракту Tau-Bench.
- Длинные диалоги могут упираться в лимит `max_prompt_chars`.

## Целевой план интеграции

### Этап 1. Protocol shakeout

Цель: убедиться, что bridge стабильно принимает историю и возвращает структурированный ответ.

Что делать:

- прогонять `tau_bridge.py` вручную на JSON-примерах;
- проверить, как извлекается `agent_reply` из лога;
- подобрать безопасный `system_prefix`;
- определить оптимальный `dialog_type`: `Агент` или `Запрос1С`.

### Этап 2. Session persistence

Цель: перестать replay-ить весь диалог каждый раз.

Что нужно добавить в 1С:

- API создания bridge-сессии;
- API добавления пользовательского сообщения в существующий диалог;
- API чтения финального ответа без парсинга полного лога.

Предпочтительный контракт:

- `СоздатьBridgeСессию(Пользователь, Метаданные)` -> `SessionId`
- `ВыполнитьХодBridge(SessionId, ТекстСообщения)` -> структура результата
- `ЗакрытьBridgeСессию(SessionId)`

### Этап 3. Native Tau adapter

Цель: подключить bridge к runtime Tau-Bench как custom agent.

Что нужно сделать:

- взять официальный контракт custom agent из Tau-Bench checkout;
- написать adapter, который на каждом user turn вызывает `tau_bridge.py` или Python API bridge;
- сохранять артефакты прогона с привязкой `tau_task_id -> 1C dialog_ref`.

### Этап 4. Tool/policy alignment

Цель: сделать результаты интерпретируемыми, а не декоративными.

Что нужно продумать:

- какие действия 1С считаются аналогом внешних tool calls;
- где граница read-only / write;
- какие операции нужно жёстко запрещать в benchmark-режиме;
- как логировать policy violations отдельно от бизнес-ошибок.

### Этап 5. Judge and scoring

Цель: не просто получить ответ агента, а честно оценить outcome.

Нужно добавить:

- адаптер оценки, который сравнивает результат 1С-агента с ожидаемым исходом задачи;
- отдельную классификацию: `reasoning_failure`, `tool_failure`, `policy_failure`, `environment_gap`;
- сопоставление с вашим локальным `quality_gate`.

## Минимальный JSON-контракт bridge

Вход:

```json
{
  "task_id": "telecom_001",
  "user_message": "Помоги поменять тариф",
  "conversation": [
    {"role": "user", "content": "Здравствуйте"},
    {"role": "assistant", "content": "Чем могу помочь?"}
  ],
  "metadata": {
    "domain": "telecom"
  }
}
```

Выход:

```json
{
  "ok": true,
  "task_id": "telecom_001",
  "user_message": "Помоги поменять тариф",
  "prompt_text": "...",
  "agent_success": true,
  "agent_reply": "...",
  "dialog_ref": "...",
  "usage_tokens": 1234,
  "log_excerpt": "...",
  "error": ""
}
```

## Примеры запуска

```powershell
python automation\tau\tau_bridge.py --text "Покажи топ контрагентов" --task-id demo_001
python automation\tau\tau_bridge.py --config .\automation\tau\tau_bridge_config.example.json --request .\automation\tau\sample_request.json --output .\automation\logs\bridge_result.json
```

## Что делать дальше в этом репозитории

Рекомендуемая последовательность:

1. Прогнать `tau_bridge.py` на 3-5 ручных сценариях.
2. Добавить явное API bridge-сессии в модуль 1С, чтобы уйти от stateless replay.
3. После этого писать native adapter под Tau-Bench runtime.
4. Только затем включать результаты в регулярный benchmark dashboard.
