@echo off
cd /d "%~dp0"
"C:\Users\Admin\miniconda3\python.exe" -m analytics.weekly_summary --db data/portfolio.db --benchmark SPY 2>&1