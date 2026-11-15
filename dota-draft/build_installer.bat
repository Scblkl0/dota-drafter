@echo off
cd /d "%~dp0"
if not exist dist\DotaDraftHelper\DotaDraftHelper.exe (
    echo dist\DotaDraftHelper\DotaDraftHelper.exe not found - run build_exe.bat first.
    pause
    exit /b 1
)
set "ISCC="
for %%P in ("%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" "%ProgramFiles%\Inno Setup 6\ISCC.exe") do (
    if exist %%P set "ISCC=%%~P"
)
if not defined ISCC (
    echo Inno Setup 6 was not found. Install it from https://jrsoftware.org/isdl.php
    pause
    exit /b 1
)
"%ISCC%" installer.iss || goto :err
echo.
echo Done: see the "installer" folder.
pause
exit /b 0
:err
echo.
echo Build failed.
pause
