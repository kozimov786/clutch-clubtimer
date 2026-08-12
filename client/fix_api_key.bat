@echo off
REM config.json'dagi api_key'ni to'g'irlaydi (git pull qilingandan keyin
REM shu faylni ishga tushiring — uzun kalitni qo'lda kiritish shart emas).
cd /d "%~dp0"
python fix_api_key.py
echo.
pause
