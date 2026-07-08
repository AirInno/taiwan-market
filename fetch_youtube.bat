@echo off
REM === Auto-fetch YouTube transcript (local, residential IP) ===
REM Logs are split monthly into logs\youtube_YYYYMM.txt with timestamp; files older than 180 days are purged.
cd /d "C:\Users\lifongye\Documents\taiwan-market"
if errorlevel 1 exit /b 1

set "LOGDIR=logs"
if not exist "%LOGDIR%" mkdir "%LOGDIR%"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMM"') do set "MONTH=%%i"
for /f "delims=" %%i in ('powershell -NoProfile -Command "Get-Date -Format 'yyyy-MM-dd HH:mm:ss'"') do set "TS=%%i"
set "LOG=%LOGDIR%\youtube_%MONTH%.txt"

echo ==== %TS% ==== >> "%LOG%"

echo [1/4] Sync with remote... >> "%LOG%"
git fetch origin >> "%LOG%" 2>&1
REM -uno: only tracked-file modifications count; untracked files are safe because reset --hard never touches them
for /f %%i in ('git status --porcelain -uno ^| find /c /v ""') do set "DIRTY=%%i"
if "%DIRTY%"=="0" (
  git reset --hard origin/main >> "%LOG%" 2>&1
) else (
  echo [WARNING] Uncommitted local changes detected - skipping reset --hard this run to avoid discarding them: >> "%LOG%"
  git status --porcelain -uno >> "%LOG%" 2>&1
)

echo [2/4] Ensure dependencies... >> "%LOG%"
python -m pip install --quiet youtube-transcript-api requests >> "%LOG%" 2>&1

echo [3/4] Fetch transcript... >> "%LOG%"
python scripts\fetch_youtube_transcript.py >> "%LOG%" 2>&1
if errorlevel 1 (
  echo [WARN] fetch_youtube_transcript.py exited with error - RSS failed after 3 retries, no new transcript this run, will retry at next schedule 11:30 or 14:30 or tomorrow >> "%LOG%"
) else (
  echo [OK] fetch_youtube_transcript.py finished normally >> "%LOG%"
)

echo [4/4] Commit and push... >> "%LOG%"
git add briefings\*-youtube-transcript.md 2>nul
git diff --staged --quiet && (echo No new transcript. >> "%LOG%" & goto END)
git commit -m "youtube-transcript: auto local fetch" >> "%LOG%" 2>&1
git push >> "%LOG%" 2>&1
if errorlevel 1 (
  echo Remote ahead, pulling... >> "%LOG%"
  git pull --rebase >> "%LOG%" 2>&1
  git push >> "%LOG%" 2>&1
)
:END
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\index.lock del /f .git\index.lock
echo [%TS%] fetch_youtube done >> "%LOG%"
powershell -NoProfile -Command "Get-ChildItem '%LOGDIR%\youtube_2*.txt' | Where-Object { $_.LastWriteTime -lt (Get-Date).AddDays(-180) } | Remove-Item -Force"
exit /b 0
