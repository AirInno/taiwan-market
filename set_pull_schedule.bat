@echo off
REM One-time: change TaiwanMarket_AutoPull schedule to 04:45 + 16:30 daily.
REM Double-click this file and approve the UAC prompt (admin required to edit Task Scheduler).
net session >nul 2>&1
if %errorLevel% neq 0 (
  echo Requesting administrator rights...
  powershell -NoProfile -Command "Start-Process -Verb RunAs -FilePath '%~f0'"
  exit /b
)

powershell -NoProfile -Command "$t1=New-ScheduledTaskTrigger -Daily -At 04:45; $t2=New-ScheduledTaskTrigger -Daily -At 16:30; Set-ScheduledTask -TaskName 'TaiwanMarket_AutoPull' -Trigger $t1,$t2 | Out-Null"
echo.
echo ===== triggers after change =====
powershell -NoProfile -Command "(Get-ScheduledTask -TaskName 'TaiwanMarket_AutoPull').Triggers | Select-Object @{n='At';e={$_.StartBoundary}} | Format-Table -Auto"
echo If you see 04:45 and 16:30 above, it worked.
echo.
pause
