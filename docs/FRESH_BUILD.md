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

Собрать CFE в тестовой ИБ, заданной `FRESH_1C_SERVER`, `FRESH_1C_REF`,
`FRESH_1C_USER`, `FRESH_1C_PASSWORD`:

```powershell
python automation/build/build_extension_fresh.py --build `
  --platform "C:\Program Files\1cv8\8.5.1.1150\bin\1cv8.exe" `
  --output bin\AI_Agent_Fresh.cfe
```

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
