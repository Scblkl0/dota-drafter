@echo off
cd /d "%~dp0"
if not exist .venv\Scripts\pythonw.exe (
    echo First run: installing libraries, please wait...
    py -m venv .venv || goto :err
    .venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt || goto :err
)
start "" .venv\Scripts\pythonw.exe main.py
exit /b 0
:err
echo.
echo Install failed. If the error mentions a long path, move this folder closer to the drive root (e.g. C:\dota-draft).
pause
