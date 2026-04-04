@echo off
cd /d "C:\Users\lifongye\Documents\taiwan-market"
echo [Sync + Fix + Backfill]
python scripts\smart_pull.py
if errorlevel 1 ( echo [ERROR] sync & pause & exit /b 1 )
python scripts\smart_pull.py --fix
python scripts\smart_pull.py --backfill
if errorlevel 1 ( echo [ERROR] backfill & pause & exit /b 1 )
echo.
echo Done! Run deploy.bat to push.
pause
