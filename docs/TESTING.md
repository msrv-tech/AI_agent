# Тестирование

Поддерживаются несколько способов тестирования: через Python HTTP-bridge, встроенный модуль ИИА_Тесты, Vanessa Automation и статический анализ BSL.

Отдельно поддерживается внешний benchmark через Tau-Bench для сравнения с публичным tool-use benchmark. Он не заменяет локальные сценарии 1С.

Как сочетать локальный benchmark и Tau-Bench на уровне KPI и release-решений: [docs/EVAL_STRATEGY.md](../docs/EVAL_STRATEGY.md)

## Запуск через run_tests.py

Скрипт `automation/ops/run_tests.py` запускает тесты через HTTP-bridge без открытия 1С:

```bash
python automation/ops/run_tests.py                    # бесплатные тесты (по умолчанию)
python automation/ops/run_tests.py --dry-run          # тесты холостого хода (mock, без ИИ)
python automation/ops/run_tests.py --with-ai          # все тесты, включая с вызовом ИИ
python automation/ops/run_tests.py --ai-only          # только боевые тесты с ИИ
python automation/ops/run_tests.py --test ТестRunQuery # один тест
python automation/ops/run_tests.py --skip-update      # пропустить обновление БД
```

Перед тестами выполняется обновление БД (xml → конфигурация → UpdateDBCfg), если не указан `--skip-update`.

## Модуль ИИА_Тесты

Общий модуль **ИИА_Тесты** предоставляет процедуры:

| Процедура | Назначение |
|-----------|------------|
| `ЗапуститьБесплатныеТесты` | Тесты без вызова ИИ (DSL, метаданные, режим Запрос1С и т.д.) |
| `ЗапуститьТестыСИИ` | Боевые тесты с реальным вызовом LLM |
| `ЗапуститьВсеТесты` | Все тесты (бесплатные + с ИИ) |
| `ЗапуститьТестыХолостойХод` | Тесты с mock-ответами, без вызова ИИ |

Бесплатные тесты также покрывают MVP-вложения, включая `mxl` и попадание контекста вложений в prompt.

## Фиктивные вызовы ИИ (моки)

Для тестов без реального ИИ используется очередь mock-ответов:

- **Установка:** `ИИА_Сервер.УстановитьОчередьMockОтветов(СсылкаДиалога, МассивMockОтветов)`
- **Очистка:** `ИИА_Сервер.ОчиститьОчередьMockОтветов(СсылкаДиалога)`

Каждый элемент массива — структура или строка, имитирующая ответ `ВызватьИИ`. При вызове ИИ в режиме холостого хода берётся следующий mock из очереди.

## Запуск через HTTP-bridge

**ИИА_ДиалогCOM.СоздатьДиалогИВыполнитьАгентаСинхронно(Пользователь, Текст, ТипДиалога)** — создаёт диалог, отправляет сообщение и выполняет оркестратор. Используется для автотестов и скриптов.

CLI-скрипт `automation/tau/run_dialog.py`:

```bash
python automation/tau/run_dialog.py --text "Покажи всех контрагентов" --type Запрос1С
python automation/tau/run_dialog.py --text "Создай документ" --type Agent --log-file run_log.txt
```

Подробнее: [automation/bridge/README.md](../automation/bridge/README.md)

## Внешний benchmark: Tau-Bench

Скрипт `automation/tau/run_tau_bench.py` запускает официальный `tau2` CLI в отдельном checkout Tau-Bench и складывает артефакты в `automation/logs/tau_bench/`.

```bash
python automation/tau/run_tau_bench.py --agent-llm gpt-4.1 --user-llm gpt-4.1
python automation/tau/run_tau_bench.py --domain telecom --num-tasks 25 --num-trials 2
python automation/tau/run_tau_bench.py --compare-local-report .\logs\examples_20260408_090000\report.json
```

Нужен локальный checkout Tau-Bench и `uv`. Путь задаётся через `TAU_BENCH_REPO` или `--tau-repo`.

Подробнее: [docs/TAU_BENCH.md](../docs/TAU_BENCH.md)
Bridge для запуска именно 1С-агента внутри внешнего benchmark-контура: [docs/TAU_AGENT_BRIDGE.md](../docs/TAU_AGENT_BRIDGE.md)
Практический запуск real-run с custom agent: [docs/TAU_REAL_RUN.md](../docs/TAU_REAL_RUN.md)
Для дешёвого и бесплатного Tau smoke/regression контура используйте `--cost-mode cheap|free`.

## Vanessa Automation

Сценарии Gherkin для UI-тестирования формы агента. Файл `TestAIAgent.feature`, запуск через `automation/vanessa/update_and_run_vanessa.py`.

Подробнее: [automation/vanessa/TestAIAgent_README.md](../automation/vanessa/TestAIAgent_README.md)

## Python UI через pywinauto

Для desktop UI-тестов тонкого клиента 1С можно использовать `pywinauto` без Vanessa.

Установка:

```bash
pip install -r automation/ui/requirements-ui.txt
```

Запуск smoke-сценария:

```bash
python automation/ui/ui_1c_agent_test.py
python automation/ui/ui_1c_agent_test.py --prompt "ответь одним словом: ОК"
```

Запуск в отдельном окне, чтобы не ронять Cursor IDE:

```bash
python automation/ui/run_ui_test_external.py
python automation/ui/run_ui_test_external.py --leave-open
python automation/ui/run_ui_test_external.py --prompt "ответь одним словом: ОК"
```

Скрипт:
- запускает тонкий клиент 1С;
- открывает форму `ИИ Агент` через боковую навигацию;
- создаёт новый диалог;
- отправляет сообщение;
- ждёт ответа и проверяет текст в окне.

Запуск с хоста через гостевого VM-агента:

```bash
python automation/ui/run_ui_test_via_vm.py
python automation/ui/run_ui_test_via_vm.py --prompt "ответь одним словом: ОК"
```

Этот режим работает так:
- хост кладёт job-файл в `automation/logs/vm_ui_jobs/pending/`
- гостевой `guest_ui_agent.py` подхватывает job в интерактивной сессии
- UI-тест выполняется в VM
- лог и артефакты сразу пишутся обратно в шару на хост

Для гостя нужен запущенный агент:

```bash
python automation/ui/guest_ui_agent.py --jobs-root H:\EDTApps\AI_agent\automation\logs\vm_ui_jobs
```

Для ручного старта 1С на русском внутри гостя:

```bash
python automation/ui/launch_1c_russian.py
```

Для создания ярлыков в гостевой Windows VM:

```bash
python automation/ui/setup_guest_launchers.py
python automation/ui/setup_guest_launchers.py --autostart
```

`--autostart` создаёт автозапуск именно `guest_ui_agent.py`, а не одного UI-теста.
Ярлыки и автозапуск должны ссылаться на код в `H:\EDTApps\AI_agent\...`, а не на локальный `C:\Work\AI_agent`.

Разовый bat-лаунчер для гостевого рабочего стола:

```bat
automation\ui\setup_guest_launchers_once.bat
```

Этот bat:
- мапит `H:` на `\\DEV1\D`
- создаёт ярлыки на код в `H:\EDTApps\AI_agent\...`
- настраивает автозапуск `guest_ui_agent.py`

Логи и артефакты:
- лог: `automation/logs/ui_pywinauto.log`
- скриншоты и dump окна при ошибке: `automation/logs/ui_artifacts/`

## Линтер BSL (BSL Language Server)

Статический анализ BSL-кода в XML-выгрузке:

```batch
automation\bsl\run-bsl-analyze.bat
```

Результаты: `automation/logs/bsl-json.json`, `automation/logs/bsl-summary.txt`.

Подробнее: [automation/bsl/BSL-README.md](../automation/bsl/BSL-README.md)
