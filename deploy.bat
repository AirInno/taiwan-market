@echo off
setlocal enabledelayedexpansion

for /f %%a in ('echo prompt $E ^| cmd') do set "E=%%a"
set "GREEN=%E%[92m"
set "RED=%E%[91m"
set "YELLOW=%E%[93m"
set "CYAN=%E%[96m"
set "RESET=%E%[0m"

echo %CYAN%==============================%RESET%
echo %CYAN%   Taiwan Market - Deploy%RESET%
echo %CYAN%==============================%RESET%
echo.

cd /d "C:\Users\lifongye\Documents\taiwan-market"
if !ERRORLEVEL! NEQ 0 (
  echo %RED%[ERROR] Folder not found.%RESET%
  goto :END
)

echo %CYAN%[0/4]%RESET% Setup helper bat files...
python scripts\smart_pull.py --setup
echo       %GREEN%OK%RESET%
echo.

echo %CYAN%[1/4]%RESET% git add files...
git add index.html deploy.bat data.json trump-briefing.json scripts\smart_pull.py scripts\update_data.py scripts\fetch_trump_news.py fix_stocks.bat backfill.bat .github\workflows\update_data.yml .github\workflows\trump_news.yml
if !ERRORLEVEL! NEQ 0 (
  echo %RED%[ERROR] git add failed.%RESET%
  goto :END
)
echo       %GREEN%OK%RESET%

echo %CYAN%[2/4]%RESET% git commit...
git commit -m "update %date% %time:~0,5%"
if !ERRORLEVEL! NEQ 0 (
  echo %YELLOW%[INFO] Nothing to commit.%RESET%
)
echo       %GREEN%OK%RESET%

echo %CYAN%[3/4]%RESET% git push...
git push 2>&1
if !ERRORLEVEL! NEQ 0 (
  echo %RED%[ERROR] git push failed.%RESET%
  goto :END
)

echo %CYAN%[4/4]%RESET% Cleanup git locks...
if exist .git\HEAD.lock  del /f .git\HEAD.lock
if exist .git\index.lock del /f .git\index.lock

echo.
echo %GREEN%==============================%RESET%
echo %GREEN%  SUCCESS! ~1 min to update.%RESET%
echo %GREEN%  https://airinno.github.io/taiwan-market/%RESET%
echo %GREEN%==============================%RESET%

:END
echo.
pause
