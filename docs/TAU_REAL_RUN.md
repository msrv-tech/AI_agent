# Реальный Прогон Tau-Bench

Ниже минимальный рабочий путь для прогона Tau-Bench именно с вашим 1С-агентом.

## Что добавлено

- [`run_tau_with_1c_agent.py`](../automation/tau/run_tau_with_1c_agent.py) — programmatic runner, который регистрирует custom agent в Tau-Bench.
- [`tau2_1c_agent.py`](../automation/tau/tau2_1c_agent.py) — custom `HalfDuplexAgent`, проксирующий ходы в 1С через bridge.
- [`tau_bridge.py`](../automation/tau/tau_bridge.py) — теперь поддерживает session mode.
- [`ИИА_ДиалогCOM`](../xml/CommonModules/ИИА_ДиалогCOM/Ext/Module.bsl) — добавлены `СоздатьBridgeСессию`, `ВыполнитьХодBridge`, `ЗакрытьBridgeСессию`.

## Что нужно в окружении

1. Локальный checkout Tau-Bench уже должен лежать в `vendor/tau2-bench`.
2. В Python должны быть установлены зависимости Tau-Bench.
3. Должен работать HTTP-bridge к 1С и быть настроен `BRIDGE_URL`.
4. Должна быть настроена модель для user simulator Tau-Bench: `TAU_BENCH_USER_LLM`.
5. Для режима с NL judge желательно задать:
   - `TAU_NL_ASSERTIONS_MODEL`
   - `TAU_NL_ASSERTIONS_API_BASE`
   - `TAU_NL_ASSERTIONS_API_KEY`
6. Для выбора дешёвого/бесплатного контура можно задать:
   - `TAU_BENCH_COST_MODE=full|cheap|free`

## Как запускать

Простой smoke-run:

```powershell
cd vendor\tau2-bench
uv run python ..\..\automation\tau\run_tau_with_1c_agent.py --domain mock --user-llm gpt-4o --num-tasks 1 --num-trials 1 --evaluation-type all
```

Бесплатный regression smoke-run для `mock`:

```powershell
cd vendor\tau2-bench
uv run python ..\..\automation\tau\run_tau_with_1c_agent.py --domain mock --cost-mode free --num-tasks 7 --num-trials 1
```

Smoke-run с NL judge:

```powershell
cd vendor\tau2-bench
uv run python ..\..\automation\tau\run_tau_with_1c_agent.py --domain mock --user-llm gpt-4o --num-tasks 1 --num-trials 1 --evaluation-type all_with_nl_assertions
```

Более реальный run:

```powershell
cd vendor\tau2-bench
uv run python ..\..\automation\tau\run_tau_with_1c_agent.py --domain telecom --user-llm gpt-4o --num-tasks 5 --num-trials 1 --verbose-logs --evaluation-type all
```

## Что означают cost-mode

- `full`: обычный run с LLM user simulator.
- `cheap`: дешёвый режим. Для `mock` использует deterministic user и выключает `nl_assertions`.
- `cheap` для `telecom`: переключает run на `small` split и выключает `nl_assertions`.
- `free`: бесплатный режим для `mock`, без внешних LLM.

Практически:

- для CI smoke/regression лучше использовать `mock + free`;
- для проверки финальной коммуникации использовать `mock + full + all_with_nl_assertions`;
- для дешёвого доменного smoke использовать `telecom + cheap`;
- для доменных оценок `telecom/retail/airline` использовать `full`.

## Что происходит внутри

1. Runner подключает `vendor/tau2-bench/src` в `PYTHONPATH`.
2. Регистрирует custom agent `onec_tau_agent`.
3. Tau-Bench orchestrator вызывает этот агент turn-by-turn.
4. Агент отправляет ход в [`tau_bridge.py`](../automation/tau/tau_bridge.py).
5. Bridge работает через HTTP session API в 1С.
6. Ответ агента возвращается в Tau-Bench как `AssistantMessage`.

## Важное ограничение

Это уже реальный runtime-прогон, но не идеальная интеграция.

Причина:

- Tau-Bench ожидает явные tool calls в своём формате.
- Ваш 1С-агент нативно работает не с tau-tools, а с внутренним 1С/DSL контуром.

Поэтому adapter использует `tool_json` prompting и пытается распарсить ответ агента в:

```json
{"tool_calls":[{"name":"tool_name","arguments":{...}}]}
```

Это даёт исполнимый evaluation loop, но не гарантирует хороший score.

Для `mock` домена добавлен более жёсткий tau-native режим, чтобы smoke-run не зависел от 1С DSL-планирования и корректно работал через `create_task`/`update_task_status`.

## Что ещё может не дать запустить прогон прямо сейчас

- В системе может не быть установленных зависимостей Tau-Bench.
- В системе может не быть `uv`.
- Может не работать HTTP-bridge/1С на этой машине.
- Может быть недоступен LLM для user simulator.

## Следующий шаг после smoke-run

Если smoke-run стартует и хотя бы проходит orchestrator loop, дальше уже имеет смысл:

1. смотреть, какие tool names чаще всего пытается вызывать агент;
2. учить bridge-подсказку под нужный JSON-формат;
3. при необходимости вводить отдельный tool planner для Tau-Bench поверх 1С-агента.

## Как читать результат

В успешном прогоне смотрите:

- `Reward: 1.0000`
- `Termination Reason: USER_STOP` или `AGENT_STOP`
- `DB Check: ✅`
- `Action Checks: ✅`
- `NL Assertions: ✅` если запускали с `all_with_nl_assertions`

Если `NL Assertions` не показываются, это нормально для `evaluation-type=all`.

## Текущий бесплатный mock-suite

Стабильный `free`-контур сейчас включает 7 задач:

- `create_task_1`
- `create_task_1_with_env_assertions`
- `update_task_1`
- `update_task_with_message_history`
- `update_task_with_initialization_actions`
- `update_task_with_history_and_env_assertions`
- `impossible_task_1`

Исключён кейс `update_task_with_initialization_data`, потому что он требует более богатого context acknowledgment, чем текущий free mock-path.
