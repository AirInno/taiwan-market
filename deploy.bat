@echo off
setlocal enabledelayedexpansion

:: Enable ANSI color support
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

echo %CYAN%[1/3]%RESET% git add files...
git add index.html deploy.bat data.json
if !ERRORLEVEL! NEQ 0 (
  echo %RED%[ERROR] git add failed.%RESET%
  goto :END
)
echo       %GREEN%OK%RESET%

echo %CYAN%[2/3]%RESET% git commit...
git commit -m "update index.html %date% %time:~0,5%"
if !ERRORLEVEL! NEQ 0 (
  echo %YELLOW%[INFO] Nothing to commit, checking if push needed...%RESET%
)
echo       %GREEN%OK%RESET%

echo %CYAN%[3/3]%RESET% git push...
git push 2>&1
if !ERRORLEVEL! NEQ 0 (
  echo.
  echo %RED%[ERROR] git push failed.%RESET%
  echo %RED%  - Check your internet connection.%RESET%
  echo %RED%  - GitHub Token may have expired.%RESET%
  goto :END
)

echo.
echo %GREEN%==============================%RESET%
echo %GREEN%  SUCCESS! Site updates in ~1 min.%RESET%
echo %GREEN%  https://airinno.github.io/taiwan-market/%RESET%
echo %GREEN%==============================%RESET%

:END
echo.
pause
