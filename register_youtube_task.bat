@echo off
REM === Register daily Windows scheduled tasks for YouTube transcript ===
set BAT="C:\Users\lifongye\Documents\taiwan-market\fetch_youtube.bat"
echo Registering daily tasks...
schtasks /create /tn "YT-Transcript-AM" /tr %BAT% /sc daily /st 11:30 /f
schtasks /create /tn "YT-Transcript-PM" /tr %BAT% /sc daily /st 14:30 /f
echo.
echo Done. Two daily tasks created: 11:30 and 14:30.
echo To remove: schtasks /delete /tn "YT-Transcript-AM" /f
echo            schtasks /delete /tn "YT-Transcript-PM" /f
pause
