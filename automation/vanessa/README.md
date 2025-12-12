# Пакет Vanessa Automation для добавления записи в Справочник2

В эту папку собраны все артефакты, которые нужны чтобы перенести автоматизацию в другой проект:

- `vanessa-automation-single.epf` – обработка Vanessa Automation (single поставка).
- `AddCatalog2TestEntry.feature` – сценарий, который открывает `Справочник2` и создаёт тестовую запись.
- `update-and-run-vanessa.ps1` – скрипт, который обновляет конфигурацию БД и запускает Vanessa с нужным сценарием.
- `VAParams.json` – пример настроек запуска (создаётся автоматически, если удалить).
- `logs\` – каталог, куда будут складываться `update-db.log` и `vanessa.log`.

## Как перенести и запустить

1. Скопируйте папку `vanessa` в новый проект.
2. Проверьте/исправьте в `update-and-run-vanessa.ps1` параметры `PlatformExe`, `ConnectionString`, а при необходимости и `UserName`/`Password`.
3. Запустите скрипт из PowerShell:

   ```powershell
   pwsh -NoLogo -NoProfile -ExecutionPolicy Bypass -File .\vanessa\update-and-run-vanessa.ps1
   ```

   (Если используете Windows PowerShell, можно заменить `pwsh` на `powershell`.)

После успешного выполнения в папке `logs` появятся файлы с результатами обновления базы и прогонки сценария.


