# Quality Gate

## Уровни проверки

### HTTP-bridge gate

Быстрый и переносимый уровень. Запускает агента через Codex Test Bridge без браузера и проверяет:

- корректный бизнес-результат;
- DSL-действия;
- recovery;
- token budget;
- отсутствие опасных write/delete-действий в read-only/safety сценариях;
- выбор подходящих объектов метаданных.

Примеры:

```bash
python automation/bridge/test_examples.py --bridge-url 'http://192.168.2.127/fresh-bp-demo/hs/codex-test' --user Admin --examples-group extended
python automation/bridge/test_examples.py --bridge-url 'http://192.168.2.127/fresh-unf/hs/codex-test' --examples-group extended
```

### Matrix gate

Релизный оркестратор. Прогоняет HTTP-bridge gate по нескольким конфигурациям и опциональные UI/E2E проверки:

- обычный агент выбирает skill;
- skill реально создает/записывает документ и показывает ссылку;
- approval branches;
- lifecycle JSON skill: вставить, сохранить, экспортировать, импортировать, запустить тест;
- negative UI: пустое описание, битый JSON, попытка перезаписать system skill;
- распознавание документов: счет поставщика, УПД/ТОРГ-12, акт услуг, счет-фактура.

Базовый релизный прогон по BP и UNF:

```powershell
python automation\quality_gate_matrix.py --group extended
```

Последний эталонный прогон без предметных prompt-правил выбора объектов:

- `matrix_20260920_104730`: PASS, 2/2 баз.
- BP `fresh-bp-demo`: 13/13, avg `90.08`, min `77`.
- UNF `fresh-unf`: 13/13, avg `91.69`, min `85`.

Полный прогон с UI:

```powershell
python automation\quality_gate_matrix.py --group extended --include-ui --document-files 'all=D:\bsl\AI_agent\temp\Счет на оплату № 6 от 26 августа 2025 г.pdf'
```

Для write-flow и распознавания с реальным созданием документов:

```powershell
python automation\quality_gate_matrix.py --group extended --include-skill-write --include-document-recognition --require-document-created --auto-confirm
```

### Cloud Fresh gate

Для опубликованного приложения на [1С:Фреш](https://1cfresh.com/a/sbm/2226502/ru_RU/) внешний HTTP-bridge обычно недоступен. Используется browser gate:

1. OpenID-вход в сервис (`FRESH_CLOUD_USER` / `FRESH_CLOUD_PASSWORD`).
2. Прогон сценариев `test_examples.py` через форму «ИИ Агент» в web-client.
3. Опционально negative UI для Skills (без bridge).

Подготовка `.env`:

```powershell
FRESH_CLOUD_WEB_URL=https://1cfresh.com/a/sbm/2226502/ru_RU/
FRESH_CLOUD_USER=ваш_логин
FRESH_CLOUD_PASSWORD=ваш_пароль
```

Базовый прогон extended-сценариев + negative UI:

```powershell
python automation\quality_gate_matrix.py --profile cloud-fresh --group extended --auto-confirm
```

Только browser gate (без Skills UI):

```powershell
python automation/ui/web_quality_gate.py --examples-group extended --auto-confirm --headed
```

Smoke-прогон (4 сценария):

```powershell
python automation\quality_gate_matrix.py --profile cloud-fresh --group smoke --auto-confirm
```

### Cloud API gate

Тот же набор сценариев `test_examples.py`, но диалог идёт через закрытый HTTP API опубликованного приложения, без браузера и без Codex Test Bridge:

1. Basic-авторизация пользователя информационной базы (`FRESH_CLOUD_USER` / `FRESH_CLOUD_PASSWORD`).
2. `POST /v1/dialogs` и `POST /v1/dialogs/{id}/send`.
3. Ожидание остановки оркестратора. Для сценариев с `auto_confirm` ожидающее подтверждение закрывается действием `approve_without_confirmation`.
4. Оценка по логу диалога и `row_count` из `GET /v1/dialogs/{id}/query-result`.
5. Распознавание документа УНФ: `POST /v1/dialogs` с типом `document_recognition`, затем `POST /v1/dialogs/{id}/attachments` с переданным файлом и обычный цикл send/poll/log. Проверяются имя навыка, имя файла и либо маркеры промпта (`РЕЖИМ: РАСПОЗНАВАНИЕ ДОКУМЕНТОВ`, `target_object_name`, `DSL_TEMPLATE_JSON`), либо факты выполнения: применённый DSL-шаблон навыка и `document_type` или созданный документ. Строка `Ошибка API` или `OpenAI API error` в логе делает шаг неуспешным. Черновик документа обязателен только с `--require-document-created`.

`ДоступнаЗапись` через API не включается: `/v1/me` только показывает текущий флаг. Обрезанный лог длиннее 200000 символов останавливает сценарий с ошибкой. Если `--document-files` не задан, берётся локальный счёт `temp/Счет на оплату № 6 от 26 августа 2025 г.pdf`. Когда этого файла нет, шаг завершается ошибкой: синтетический файл не создаётся. Облачная база — УНФ, поэтому цели такие: `СчетНаОплатуПоставщика`, `ПриходнаяНакладная`, `АктВыполненныхРабот`, `СчетФактураПолученный`. Ключ `all` запускает все четыре сценария на одном файле; путь без ключа запускает только счёт поставщика.

```bash
python automation/quality_gate_matrix.py --profile cloud-api --group smoke --score-mode heuristic \
  --document-files "/path/to/invoice.pdf" --auto-confirm
python automation/quality_gate_matrix.py --profile cloud-api --group extended --score-mode heuristic \
  --document-files "supplier_invoice=/path/to/invoice.pdf;upd_torg12=/path/to/upd.pdf" --auto-confirm
```

Прямой запуск одного прогона:

```bash
python automation/bridge/test_examples.py \
  --agent-api-url https://1cfresh.com/a/sbm/2226502/hs/iia-agent \
  --user "$FRESH_CLOUD_USER" \
  --password "$FRESH_CLOUD_PASSWORD" \
  --examples-group smoke \
  --score-mode heuristic
```

Пороги успеха те же: все сценарии passed, avg score ≥ 70, min score ≥ 40.

## Что Считается Успехом

- Не только текст "успешно", а системные факты: `RunQuery`, `CreateDocument`, `Write`, измененные объекты, найденный документ по маркеру, ссылка в форме агента.
- Для пустого результата должен быть структурный признак `row_count=0` и понятный `ShowInfo`.
- Для опасных операций не должно быть `Write`, `SetField`, `CreateDocument`, `CreateReference`, `DeleteObject` без разрешенной политики.
- Для переносимости один и тот же сценарий должен проходить минимум на BP и UNF.

## Когда Добавлять Новый Сценарий

- Появился новый тип пользовательского намерения.
- Исправлен recovery-баг, который мог вернуться.
- Добавлена новая DSL action или capability.
- Добавлен новый тип skill или `dsl_template`.
- Появилась поддержка новой конфигурации 1С.
