@echo off
cd /d "C:\Users\lifongye\Documents\taiwan-market"
echo [Fix Stock Rankings]
python scripts\smart_pull.py --fix
if errorlevel 1 ( echo [ERROR] & pause & exit /b 1 )
echo.
echo Done! Run deploy.bat to push.
pause
