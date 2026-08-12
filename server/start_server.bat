@echo off
REM Clutch Zone — Django/Daphne serverini ishga tushiradi.
REM Avval ..\venv\Scripts\python.exe bor-yo'qligini tekshiradi, bo'lmasa
REM PATH'dagi tizim python'iga o'tadi (kassa serverida venv topilmagani
REM uchun shu fallback qo'shildi).
cd /d "%~dp0"

if exist "..\venv\Scripts\python.exe" (
    set "PY=..\venv\Scripts\python.exe"
) else (
    set "PY=python"
)

echo [Server] %PY% ishlatilmoqda.
echo [Server] Baza yangilanmoqda (migrate)...
%PY% manage.py migrate

echo [Server] Daphne ishga tushirilmoqda (0.0.0.0:8000)...
%PY% -m daphne -b 0.0.0.0 -p 8000 config.asgi:application
