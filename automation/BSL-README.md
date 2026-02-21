# BSL Language Server — статический анализ кода

Статический анализ BSL‑кода в XML‑выгрузке расширения 1С с помощью [BSL Language Server](https://1c-syntax.github.io/bsl-language-server/).

## Требования

- **Java** JRE 11+ (для запуска JAR)
- **Python 3** (для постобработки отчёта; использует только стандартную библиотеку)

## Установка JAR

1. Скачайте исполняемый JAR с [GitHub Releases](https://github.com/1c-syntax/bsl-language-server/releases):
   - для версии 0.28.4: `bsl-language-server-0.28.4-exec.jar`
   - или более новую: `bsl-language-server-*-exec.jar`
2. Поместите файл в каталог `automation`:
   ```
   automation/
   └── bsl-language-server-0.28.4-exec.jar
   ```
3. Если используете другую версию — переименуйте файл или измените имя в `run-bsl-analyze.bat`.

## Запуск

Из каталога `automation`:

```batch
run-bsl-analyze.bat
```

Либо двойной клик по `run-bsl-analyze.bat`.

## Результаты

- `automation/logs/bsl-json.json` — полный JSON‑отчёт от BSL LS
- `automation/logs/bsl-summary.txt` — краткий текстовый отчёт (только Error и Warning)

## Структура

```
automation/
├── run-bsl-analyze.bat        # точка входа
├── bsl_report_summary.py      # постпроцессор JSON → текст
├── bsl-language-server-*.jar  # скачать отдельно
└── logs/
    ├── bsl-json.json          # выход BSL LS
    └── bsl-summary.txt        # краткий отчёт
```
