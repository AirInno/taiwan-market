@echo off
cd /d "C:\Users\lifongye\Documents\taiwan-market"
echo [Historical Backfill] 20251001 ~ 20260228
echo.
python scripts\backfill_history.py --start 20251001 --end 20260228
if errorlevel 1 ( echo [ERROR] backfill failed & pause & exit /b 1 )
echo.
echo [Auto Push] Pushing to GitHub...
git add data.json
git diff --staged --quiet && (
  echo [INFO] No new data, skipping push
) || (
  git commit -m "backfill history 20251001-20260228"
  git push
  if errorlevel 1 ( echo [ERROR] push failed & pause & exit /b 1 )
  echo [OK] Pushed to GitHub
)
echo.
echo Done!
pause
