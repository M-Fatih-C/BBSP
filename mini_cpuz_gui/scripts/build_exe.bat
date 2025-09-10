@echo off
setlocal

REM Build one-file, windowed executable with resources
pyinstaller --noconfirm --windowed --onefile ^
  --name MiniCPUZ ^
  --add-data "app/resources/report_template.html;resources" ^
  app/gui_main.py

echo.
echo Done. Output: dist\MiniCPUZ.exe
endlocal
