@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\python.exe (
    echo Run run.bat once first - it creates the Python environment.
    pause
    exit /b 1
)
.venv\Scripts\python.exe -m pip install --quiet --disable-pip-version-check pyinstaller || goto :err
.venv\Scripts\python.exe -m PyInstaller --noconfirm --clean --windowed --onedir ^
    --name DotaDraftHelper --icon icon.ico --add-data "icon.ico;." main.py || goto :err
echo.
echo Done: dist\DotaDraftHelper\DotaDraftHelper.exe
pause
exit /b 0
:err
echo.
echo Build failed.
pause
