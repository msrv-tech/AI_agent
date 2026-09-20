# Сборка редакции для 1С:Фреш

Fresh-редакция собирается из общих XML-исходников скриптом
`automation/build/build_extension_fresh.py`. Общие исходники не изменяются: адаптация
выполняется в `temp/fresh_build/xml`.

Скрипт автоматически:

- удаляет UI и код самообновления;
- удаляет обращения к `РасширенияКонфигурации` и GitHub API;
- отключает серверную запись отладочного лога по произвольному пути;
- ограничивает выбор ИИ-провайдера вариантами GitSell, GigaChat и Yandex AI Studio;
- использует корректную авторизацию для каждого из трёх провайдеров;
- проверяет, что запрещённые Fresh-маркеры не остались;
- сохраняет `МиграцияПриложений` и все записи `AutoRecord=Deny`.

Только подготовить XML:

```powershell
python automation/build/build_extension_fresh.py --prepare-only
```

Собрать CFE в лицензированной тестовой ИБ (`FRESH_1C_SERVER` / `FRESH_1C_REF`
из `.env` или реестра test-databases):

```bash
python3 automation/build/build_extension_fresh.py --build \
  --platform /opt/1cv8/x86_64/8.5.1.1150/1cv8 \
  --output bin/AI_Agent_Fresh.cfe
```

`--temp-ib` собирает во временной файловой ИБ и удаляет её после выгрузки.
На сервере без локальной программной лицензии Designer ответит
«Не найдена лицензия» — это ошибка, а не повод переключаться на другую базу.

## Деплой актуальной версии в 1С:Фреш

Воспроизводимый вход: `automation/ops/deploy_fresh.py`. Он читает `<Version>`
из `xml/Configuration.xml`, собирает `bin/AI_Agent_Fresh_<version>.cfe` и
загружает новую версию карточки «ИИ агент» в Менеджере сервиса
(`https://1cfresh.com/a/adm/ru_RU/`).

Только сборка:

```bash
python3 automation/ops/deploy_fresh.py --build-only \
  --platform /opt/1cv8/x86_64/8.5.1.1150/1cv8 \
  --server onec-server-linux:2541 \
  --ref unf_test_2 \
  --ib-user Администратор
```

Сборка и загрузка новой версии:

```bash
pip install -r automation/ops/requirements-fresh.txt
python3 -m playwright install chromium
python3 automation/ops/deploy_fresh.py \
  --platform /opt/1cv8/x86_64/8.5.1.1150/1cv8
```

Нужны `FRESH_CLOUD_USER` и `FRESH_CLOUD_PASSWORD` в `.env`. Либо готовый
Playwright storage state в `FRESH_AUTH_STATE`.

`--draft` останавливает мастер до «Завершить». Без этого флага мастер
завершается и Fresh запускает автоматическую проверку версии.
Установка в абонентское приложение и выдача прав клиентам скриптом
не выполняются.

После выгрузки CFE скрипт возвращает в сборочную ИБ обычные `xml/`, чтобы
там не осталась Fresh-редакция. `--keep-fresh-ib` это отключает.

Для карточки Fresh нужно запросить серверный доступ к следующим ресурсам:

- `gitsell.ru:443` — GitSell API и device-авторизация;
- `api.giga.chat:443` — GigaChat API;
- `ngw.devices.sberbank.ru:9443` — получение OAuth-токена GigaChat;
- `ai.api.cloud.yandex.net:443` — Yandex AI Studio.

GitSell выбран по умолчанию и использует существующую device-авторизацию.
Для GigaChat пользователь вводит Authorization Key, для Yandex AI Studio —
API-ключ и URI модели с идентификатором каталога. Произвольный
OpenAI-совместимый URL остаётся доступен только в обычной desktop-редакции.

Доступ к GitHub Fresh-редакции не требуется: версии управляются
через Менеджер сервиса.
