# Запуск через COM

Подключение к базе 1С и выполнение запросов из Python через COM (V83.COMConnector / V82.COMConnector).

## Установка

```bash
cd automation
pip install -r requirements-com.txt
```

## Использование из командной строки

Строка подключения — из переменной окружения **`1C_CONNECTION_STRING`** (та же, что в скриптах сборки) или через параметр `--connection`.

```bash
# Из корня репозитория (путь к базе — по умолчанию из 1C_CONNECTION_STRING или из config)
python -m automation.com_1c --query "ВЫБРАТЬ 1 КАК Номер" --columns Номер --json

# Явная строка подключения (файловая база)
python -m com_1c -c "File=\"D:\EDT_base\КонфигурацияТест\";" -q "ВЫБРАТЬ 1 КАК Х" --columns Х --json

# Запрос с несколькими колонками
python -m com_1c --query "ВЫБРАТЬ ПЕРВЫЕ 5 Ссылка, Наименование ИЗ Справочник.Контрагенты" --columns Ссылка,Наименование -v
```

Параметры:

- `--connection`, `-c` — строка подключения к 1С
- `--query`, `-q` — текст запроса на языке запросов 1С
- `--columns` — имена колонок через запятую (псевдонимы из запроса)
- `--json` — вывести результат в JSON
- `--verbose`, `-v` — подробный вывод

## Использование из кода

```python
from com_1c import connect_to_1c, execute_query

conn = connect_to_1c('File="D:\\EDT_base\\КонфигурацияТест";')
if conn:
    rows = execute_query(
        conn,
        "ВЫБРАТЬ ПЕРВЫЕ 3 Ссылка, Наименование ИЗ Справочник.Контрагенты",
        ["Ссылка", "Наименование"],
    )
    for row in rows:
        print(row)
```

## Запуск из PowerShell

Рекомендуется использовать скрипт `run-com.ps1` из каталога `automation`:

```powershell
cd d:\EDTApps\AI_agent\automation
.\run-com.ps1 -Query "ВЫБРАТЬ 1 КАК Номер" -Columns "Номер" -Json
.\run-com.ps1 -Connection 'File="D:\EDT_base\КонфигурацияТест";' -Query "ВЫБРАТЬ ПЕРВЫЕ 5 Наименование ИЗ Справочник.Контрагенты" -Columns "Наименование"
```

Вручную (из каталога `automation`):

```powershell
$env:PYTHONPATH = (Get-Location).Path
python -m com_1c --query "ВЫБРАТЬ 1 КАК Номер" --columns Номер
```

## Файл .env (переменная 1C_CONNECTION_STRING)

Строку подключения можно задать один раз в файле **`.env`** в корне проекта — её подхватят скрипты сборки и запуск через COM.

```powershell
# В корне репозитория (d:\EDTApps\AI_agent\):
copy .env.example .env
# Отредактируйте .env, укажите свою базу:
# 1C_CONNECTION_STRING=File="D:\EDT_base\КонфигурацияТест";
```

- **Python**: `update_1c.py` при старте читает `.env` (1C_CONNECTION_STRING).
- **PowerShell**: `vanessa/update-and-run-vanessa.ps1` также читает `.env`.
- **Python** (`python -m com_1c`, `run-com.ps1`): используется `python-dotenv`, загружается `.env` из корня проекта.
- Файл `.env` в `.gitignore` — в репозиторий не попадает. В репозитории лежит только `.env.example`.
- При передаче `-ConnectionString` в скрипты сборки параметр имеет приоритет над `.env`.

## Требования

- Windows, установленная платформа 1С:Предприятие (8.2 или 8.3)
- Python 3.7+ с установленным `pywin32`
- **Запуск от имени администратора** — PowerShell (и при необходимости `python -m com_1c`) нужно запускать от имени администратора для корректной работы COM с 1С.
