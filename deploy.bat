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
git add index.html deploy.bat data.json data-latest.json trump-briefing.json holder-weekly.json briefing-tw-instructions.md briefing-trump-instructions.md briefing-health-instructions.md scripts\smart_pull.py scripts\update_data.py scripts\update_global.py scripts\fetch_trump_news.py scripts\backfill_history.py scripts\heal.py scripts\test_pipeline.py scripts\update_holders.py scripts\generate_briefing.py scripts\log_traffic.py fix_stocks.bat backfill.bat backfill_history.bat .github\workflows\update_data.yml .github\workflows\update_global.yml .github\workflows\trump_news.yml .github\workflows\validate_and_heal.yml .github\workflows\update_trump_briefing_json.yml .github\workflows\trump_briefing_email.yml .github\workflows\tw_briefing_email.yml .github\workflows\update_holders.yml .github\workflows\monthly_review_email.yml .github\workflows\youtube_transcript.yml .github\workflows\youtube_briefing_email.yml .github\workflows\traffic_logger.yml
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

echo %CYAN%[3/4]%RESET% git push (auto sync remote)...
git push 2>&1
if !ERRORLEVEL! NEQ 0 (
  echo %YELLOW%[INFO] Remote ahead, pulling first...%RESET%
  for /f %%c in ('git stash list ^| find /c /v ""') do set "STASH_BEFORE=%%c"
  git stash
  for /f %%c in ('git stash list ^| find /c /v ""') do set "STASH_AFTER=%%c"
  git pull --rebase
  if !STASH_AFTER! GTR !STASH_BEFORE! (
    git stash pop
  ) else (
    echo       %YELLOW%[INFO] No new stash created, skip pop.%RESET%
  )
  git push 2>&1
  if !ERRORLEVEL! NEQ 0 (
    echo %RED%[ERROR] git push failed after pull.%RESET%
    goto :END
  )
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
