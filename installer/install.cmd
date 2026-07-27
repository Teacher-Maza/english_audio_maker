@echo off
setlocal
set "STAGE=%TEMP%\EAMV2-Pilot-%RANDOM%-%RANDOM%"
mkdir "%STAGE%" >nul 2>&1
powershell.exe -NoProfile -NonInteractive -Command "Expand-Archive -LiteralPath '%~dp0payload.zip' -DestinationPath '%STAGE%' -Force"
if errorlevel 1 exit /b 10
"%STAGE%\runtime\python.exe" -B "%~dp0installer_bootstrap.py" --payload "%STAGE%"
set "RESULT=%ERRORLEVEL%"
rmdir /s /q "%STAGE%" >nul 2>&1
exit /b %RESULT%
