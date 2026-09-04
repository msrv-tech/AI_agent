# Quality Gate

## Уровни проверки

### COM gate

Быстрый и переносимый уровень. Запускает агента через COM без браузера и проверяет:

- корректный бизнес-результат;
- DSL-действия;
- recovery;
- token budget;
- отсутствие опасных write/delete-действий в read-only/safety сценариях;
- выбор подходящих объектов метаданных.

Примеры:

```powershell
python automation\com_1c\test_examples.py --connection 'Srvr="192.168.2.126:2541";Ref="fresh-bp-demo";Usr="Администратор";Pwd="";' --examples-group extended
python automation\com_1c\test_examples.py --connection 'Srvr="192.168.2.126:2541";Ref="fresh-unf";Usr="Администратор";Pwd="";' --examples-group extended
```

### Matrix gate

Релизный оркестратор. Прогоняет COM gate по нескольким конфигурациям и опциональные UI/E2E проверки:

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

- `matrix_20260804_150249`: PASS, 2/2 баз.
- BP `fresh-bp-demo`: 13/13, avg `89.31`, min `67`.
- UNF `fresh-unf`: 13/13, avg `91.62`, min `83`.

Полный прогон с UI:

```powershell
python automation\quality_gate_matrix.py --group extended --include-ui --document-files 'all=D:\bsl\AI_agent\temp\Счет на оплату № 6 от 26 августа 2025 г.pdf'
```

Для write-flow и распознавания с реальным созданием документов:

```powershell
python automation\quality_gate_matrix.py --group extended --include-skill-write --include-document-recognition --require-document-created --auto-confirm
```

### Cloud Fresh gate

Для опубликованного приложения на [1С:Фреш](https://1cfresh.com/a/sbm/2226502/ru_RU/) COM и HTTP bridge недоступны снаружи. Используется browser gate:

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

Только browser COM gate (без Skills UI):

```powershell
python automation\ui\web_com_gate.py --examples-group extended --auto-confirm --headed
```

Smoke-прогон (4 сценария):

```powershell
python automation\quality_gate_matrix.py --profile cloud-fresh --group smoke --auto-confirm
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
