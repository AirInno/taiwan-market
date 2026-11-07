@echo off
cd /d "%~dp0"
echo [Fix Stock Rankings]
python scripts\smart_pull.py --fix
if errorlevel 1 ( echo [ERROR] & pause & exit /b 1 )
echo.
echo Done! Run deploy.bat to push.
pause
