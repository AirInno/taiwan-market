@echo off
cd /d "%~dp0"
echo ============================================
echo  補填歷史外資持股比率
echo  預計約 2 分鐘，請勿關閉此視窗
echo ============================================
echo.
python scripts/backfill_holdings.py
echo.
pause
