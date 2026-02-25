# Тестирование

Поддерживаются несколько способов тестирования: через Python (COM), встроенный модуль ИИА_Тесты, Vanessa Automation и статический анализ BSL.

## Запуск через run_tests.py

Скрипт `automation/run_tests.py` запускает тесты через COM без открытия 1С:

```bash
cd automation
python run_tests.py                    # бесплатные тесты (по умолчанию)
python run_tests.py --dry-run          # тесты холостого хода (mock, без ИИ)
python run_tests.py --with-ai          # все тесты, включая с вызовом ИИ
python run_tests.py --ai-only          # только боевые тесты с ИИ
python run_tests.py --test ТестRunQuery # один тест
python run_tests.py --skip-update      # пропустить обновление БД
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

## Фиктивные вызовы ИИ (моки)

Для тестов без реального ИИ используется очередь mock-ответов:

- **Установка:** `ИИА_Сервер.УстановитьОчередьMockОтветов(СсылкаДиалога, МассивMockОтветов)`
- **Очистка:** `ИИА_Сервер.ОчиститьОчередьMockОтветов(СсылкаДиалога)`

Каждый элемент массива — структура или строка, имитирующая ответ `ВызватьИИ`. При вызове ИИ в режиме холостого хода берётся следующий mock из очереди.

## Запуск через COM (CLI-аналог)

**ИИА_ДиалогCOM.СоздатьДиалогИВыполнитьАгентаСинхронно(Пользователь, Текст, ТипДиалога)** — создаёт диалог, отправляет сообщение и выполняет оркестратор синхронно (без фоновых заданий). Используется для автотестов и скриптов.

CLI-скрипт `automation/run_dialog.py`:

```bash
python run_dialog.py --text "Покажи всех контрагентов" --type Запрос1С
python run_dialog.py --text "Создай документ" --type Agent --log-file run_log.txt
```

Подробнее: [automation/com_1c/README.md](../automation/com_1c/README.md)

## Vanessa Automation

Сценарии Gherkin для UI-тестирования формы агента. Файл `TestAIAgent.feature`, запуск через `update-and-run-vanessa.ps1`.

Подробнее: [automation/vanessa/TestAIAgent_README.md](../automation/vanessa/TestAIAgent_README.md)

## Линтер BSL (BSL Language Server)

Статический анализ BSL-кода в XML-выгрузке:

```batch
cd automation
run-bsl-analyze.bat
```

Результаты: `automation/logs/bsl-json.json`, `automation/logs/bsl-summary.txt`.

Подробнее: [automation/BSL-README.md](../automation/BSL-README.md)
