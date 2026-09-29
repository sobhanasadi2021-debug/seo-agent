@echo off
chcp 65001 >nul
title SEO/GEO Agent - سئو ایجنت
cd /d "%~dp0"
start "" http://127.0.0.1:8791
python app.py
pause
