@echo off
chcp 65001 > nul
setlocal

rem UTF-8 для вывода Java (кириллица в логах)
set "JAVA_OPTS=-Dfile.encoding=UTF-8"

set "SCRIPT_DIR=%~dp0"
set "LOGS_DIR=%SCRIPT_DIR%logs"
set "JAR=%SCRIPT_DIR%bsl-language-server-0.28.4-exec.jar"
set "XML_DIR=%SCRIPT_DIR%..\xml"

if not exist "%LOGS_DIR%" mkdir "%LOGS_DIR%"

if not exist "%JAR%" (
    echo Ошибка: JAR не найден: %JAR%
    echo Скачайте bsl-language-server с https://github.com/1c-syntax/bsl-language-server/releases
    echo и поместите bsl-language-server-*-exec.jar в папку automation
    exit /b 1
)

if not exist "%XML_DIR%" (
    echo Ошибка: Каталог xml не найден: %XML_DIR%
    exit /b 1
)

echo Анализ BSL: %XML_DIR%
echo.

java %JAVA_OPTS% -jar "%JAR%" --analyze --srcDir "%XML_DIR%" --reporter json -o "%LOGS_DIR%" -q

python "%SCRIPT_DIR%bsl_report_summary.py"
set "SUMMARY=%LOGS_DIR%\bsl-summary.txt"
if exist "%SUMMARY%" (
    echo.
    echo Готово. Краткий отчёт: %SUMMARY%
)
exit /b 0
