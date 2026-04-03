@echo off
setlocal enabledelayedexpansion
for /f %%a in ('echo prompt $E ^| cmd') do set "E=%%a"
set "GREEN=%E%[92m"
set "RED=%E%[91m"
set "CYAN=%E%[96m"
set "RESET=%E%[0m"
echo %CYAN%=============================%RESET%
echo %CYAN%   Backfill Missing Data%RESET%
echo %CYAN%=============================%RESET%
echo.
cd /d "C:\Users\lifongye\Documents\taiwan-market"
if exist .git\HEAD.lock  del /f .git\HEAD.lock
if exist .git\index.lock del /f .git\index.lock
echo %CYAN%[1/3]%RESET% Smart pull...
python scripts\smart_pull.py
if !ERRORLEVEL! NEQ 0 ( echo %RED%[ERROR]%RESET% & goto :END )
echo.
echo %CYAN%[2/3]%RESET% Fix empty rankings...
python scripts\smart_pull.py --fix
echo.
echo %CYAN%[3/3]%RESET% Backfill missing days...
python scripts\smart_pull.py --backfill
if !ERRORLEVEL! NEQ 0 ( echo %RED%[ERROR]%RESET% & goto :END )
echo.
echo %GREEN%Done! Run deploy.bat to push.%RESET%
:END
echo.
pause
