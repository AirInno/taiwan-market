@echo off
cd /d "C:\Users\lifongye\Documents\taiwan-market"
echo [Sync + Fix + Backfill + Auto Push]
python scripts\smart_pull.py
if errorlevel 1 ( echo [ERROR] sync & pause & exit /b 1 )
python scripts\smart_pull.py --fix
python scripts\smart_pull.py --backfill
if errorlevel 1 ( echo [ERROR] backfill & pause & exit /b 1 )
echo.
echo [Auto Push] 推送資料到 GitHub...
git add data.json
git diff --staged --quiet && (
  echo [INFO] 無新資料，跳過 push
) || (
  git commit -m "backfill %date% %time:~0,5%"
  git push
  if errorlevel 1 ( echo [ERROR] push failed & pause & exit /b 1 )
  echo [OK] 已推送到 GitHub
)
echo.
echo Done!
pause
