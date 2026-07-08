@echo off
REM === Manual test: run fetch, show result, keep window open ===
cd /d "C:\Users\lifongye\Documents\taiwan-market"
echo Running fetch (output is also saved to youtube_test_log.txt)...
echo.
call fetch_youtube.bat > youtube_test_log.txt 2>&1
type youtube_test_log.txt
echo.
echo ===================================================
echo Finished. Log saved to youtube_test_log.txt
echo ===================================================
pause
