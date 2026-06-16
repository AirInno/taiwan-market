@echo off
REM === Auto-fetch YouTube transcript (local, residential IP) ===
cd /d "C:\Users\lifongye\Documents\taiwan-market"
if errorlevel 1 exit /b 1

echo [1/4] Sync with remote...
git fetch origin
git reset --hard origin/main

echo [2/4] Ensure dependencies...
python -m pip install --quiet youtube-transcript-api requests

echo [3/4] Fetch transcript...
python scripts\fetch_youtube_transcript.py

echo [4/4] Commit and push...
git add briefings\*-youtube-transcript.md 2>nul
git diff --staged --quiet && (echo No new transcript. & goto END)
git commit -m "youtube-transcript: auto local fetch"
git push
if errorlevel 1 (
  echo Remote ahead, pulling...
  git pull --rebase
  git push
)
:END
if exist .git\HEAD.lock del /f .git\HEAD.lock
if exist .git\index.lock del /f .git\index.lock
exit /b 0
