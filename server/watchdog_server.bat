@echo off
REM Clutch Zone Server — watchdog: Daphne kutilmaganda to'xtasa (xato,
REM elektr uzilishidan keyingi qayta yoqilish va h.k.), avtomatik qayta
REM ishga tushiradi. Server doim ishlab turishi kerak bo'lgani uchun
REM (client watchdog'dan farqli o'laroq) hech qanday "toza chiqish"
REM holati yo'q — har doim qayta ishga tushiradi.
cd /d "%~dp0"

:loop
echo [Watchdog] Server ishga tushirilmoqda...
call start_server.bat
echo [Watchdog] Server to'xtadi. 5 soniyadan keyin qayta ishga tushiriladi...
timeout /t 5 /nobreak >nul
goto loop
