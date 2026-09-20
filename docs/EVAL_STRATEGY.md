# Стратегия оценки агента

Этот документ фиксирует, как использовать локальный benchmark и Tau-Bench вместе.

Коротко:

- локальный benchmark остаётся основным KPI;
- Tau-Bench используется как внешний benchmark и regression/stress слой;
- результаты этих контуров нельзя смешивать в один score без оговорок.

## Роли контуров

### Локальный benchmark

Отвечает на вопрос:

`Решает ли агент реальные 1С-задачи правильно и безопасно?`

Это основной источник решения о качестве релиза.

### Tau-Bench

Отвечает на вопрос:

`Насколько агент зрелый как tool-using service agent по внешнему стандарту?`

Это внешний контур сравнения, который полезен для regression, stress-тестов и проверки agent loop вне ваших внутренних сценариев.

## Что мерить

### В локальном benchmark

- `Task success rate` по реальным 1С-сценариям.
- `Business correctness`: корректность созданных и изменённых объектов.
- `Safety/compliance`: нарушения прав, опасные действия, нарушение бизнес-правил.
- `Recovery rate`: устойчивость к неполным данным, ошибкам 1С и неоднозначным запросам.
- `Latency`, `cost`, число шагов, число DSL-вызовов.

### В Tau-Bench

- `Reward / success rate`.
- `Action match`: правильный ли tool вызван и с правильными ли аргументами.
- `DB / env assertions`: пришла ли среда в ожидаемое состояние.
- `NL assertions`: корректно ли агент завершил коммуникацию.
- `Termination reason`: `user_stop`, `agent_stop`, `max_steps`, `infra error`.

## KPI на дашборде

### Основной KPI

- `Internal success rate` по локальному benchmark.

### Внешние KPI

- `Tau success rate` по `mock`.
- `Tau success rate` по доменным наборам, например `telecom`.

### Guardrail metrics

- `policy violations`
- `infra failures`
- `max_steps rate`
- `average latency`
- `average tool calls per task`
- `average cost per task`

Рекомендуется держать эти метрики раздельно:

- локальный 1С smoke;
- локальный 1С regression;
- Tau `mock`;
- Tau доменные прогоны.

## Как интерпретировать результаты

### Хороший сигнал

- локальный benchmark зелёный;
- Tau-Bench зелёный.

Это означает, что агент стабилен и в вашей предметной области, и во внешнем tool-use контуре.

### Локальный зелёный, Tau красный

Обычно это означает одно из двух:

- агент хорошо адаптирован под ваши кейсы, но слабее как общий tool-using agent;
- в адаптере Tau-Bench есть проблемы с policy loop, turn-taking или tool contract.

### Локальный красный, Tau зелёный

Обычно это означает, что агент в целом способен решать benchmark-задачи, но недостаточно адаптирован к вашей 1С-предметной области.

### Частые сигналы в Tau-Bench

- `Reward=1.0`, `DB=true`, `Action=true`, `NL=true`:
  полный pass.
- `Action=true`, `DB=false`:
  агент вызвал правильный tool, но не добился нужного состояния.
- `DB=true`, `NL=false`:
  задачу сделал, но плохо завершил разговор.
- `max_steps`:
  агент зациклился или не умеет корректно завершать сценарий.
- `infra error`:
  проблема окружения, LLM endpoint, judge или рантайма; по этому результату нельзя судить о качестве агента.

## Наборы прогонов

### На каждый PR

- быстрый локальный smoke;
- Tau `mock` smoke без `nl_assertions`;
- Tau `mock` с `nl_assertions`, если менялся prompt, adapter или tool layer.

### Nightly

- расширенный локальный regression;
- Tau `mock` regression;
- один узкий доменный Tau smoke/regression, например `telecom`.

### Перед release

- полный локальный benchmark;
- Tau regression по выбранным доменам;
- сравнение с предыдущим релизом по success, latency, cost и policy violations.

## Минимальный практический набор

Если нужен минимальный и полезный контур, достаточно держать 4 запуска:

- локальный 1С smoke;
- локальный 1С regression;
- Tau `mock` regression;
- Tau `telecom` smoke.

Этого уже достаточно, чтобы:

- ловить поломки в 1С-логике;
- ловить поломки agent loop;
- видеть разницу между доменной деградацией и внешней tool-use деградацией.

## Что считается источником истины

Для решения о качестве релиза:

- источник истины номер один: локальный benchmark;
- источник истины номер два: guardrail-метрики;
- Tau-Bench используется как внешний контроль и regression-сетка.

Tau-Bench не должен в одиночку блокировать или выпускать релиз без контекста локальных 1С-сценариев.

## Связанные документы

- [docs/TESTING.md](../docs/TESTING.md)
- [docs/TAU_BENCH.md](../docs/TAU_BENCH.md)
- [docs/TAU_REAL_RUN.md](../docs/TAU_REAL_RUN.md)
