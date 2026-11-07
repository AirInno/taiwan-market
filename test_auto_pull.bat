@echo off
REM Manual test: run auto_pull, then show this month's log tail and keep window open.
echo ===== run auto_pull.bat =====
call "%~dp0auto_pull.bat"
echo.
echo ===== this month log (last 15 lines) =====
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMM"') do set "MONTH=%%i"
powershell -NoProfile -Command "Get-Content '%~dp0logs\pull_%MONTH%.txt' -Tail 15"
echo.
echo ===== current HEAD =====
cd /d "%~dp0"
git log --oneline -1
echo.
pause
