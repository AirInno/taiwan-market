@echo off
REM taiwan-market auto sync (Task Scheduler daily 04:45 / 16:30)
REM Logs are split monthly into logs\pull_YYYYMM.txt with timestamp; files older than 180 days are purged.
cd /d "C:\Users\lifongye\Documents\taiwan-market"
set "REPO=C:\Users\lifongye\Documents\taiwan-market"
set "LOGDIR=%REPO%\logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"

for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMM"') do set "MONTH=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set "TS=%%i"
set "LOG=%LOGDIR%\pull_%MONTH%.txt"

echo ==== %TS% ====>> "%LOG%"
git fetch origin >> "%LOG%" 2>&1

REM -uno: only tracked-file modifications count; untracked files are safe because reset --hard never touches them
for /f %%i in ('git status --porcelain -uno ^| find /c /v ""') do set "DIRTY=%%i"
if "%DIRTY%"=="0" (
  git reset --hard origin/main >> "%LOG%" 2>&1
) else (
  echo [WARNING] Uncommitted local changes detected - skipping reset --hard this run to avoid discarding them: >> "%LOG%"
  git status --porcelain -uno >> "%LOG%" 2>&1
)
echo.>> "%LOG%"

powershell -NoProfile -Command "Get-ChildItem '%LOGDIR%\pull_2*.txt' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-180) } | Remove-Item -Force"
