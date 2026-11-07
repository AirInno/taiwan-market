@echo off
REM One-time: set TaiwanMarket_AutoPull scheduled task to run with a hidden window.
REM Double-click this file and approve the UAC prompt (admin required to edit Task Scheduler).
net session >nul 2>&1
if %errorLevel% neq 0 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

powershell -NoProfile -Command "$t=Get-ScheduledTask -TaskName 'TaiwanMarket_AutoPull'; $s=$t.Settings; $s.Hidden=$true; Set-ScheduledTask -TaskName 'TaiwanMarket_AutoPull' -Settings $s | Out-Null"
echo.
echo ===== Hidden setting after change =====
powershell -NoProfile -Command "(Get-ScheduledTask -TaskName 'TaiwanMarket_AutoPull').Settings.Hidden"
echo If you see True above, it worked.
echo.
pause
