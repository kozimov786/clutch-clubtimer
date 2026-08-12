@echo off
REM Clutch Zone Client Locker — watchdog
REM client_locker.py kutilmaganda qulasa (xato bilan chiqsa), avtomatik
REM qayta ishga tushiradi. Agar dastur ATAYLAB yopilgan bo'lsa (masalan
REM Ctrl+Shift+P favqulodda chiqish orqali, os._exit(0) bilan, kod 0),
REM qayta ishga tushirmaydi — bu holda xodim Windows ish stoliga ataylab
REM chiqqan bo'ladi.
cd /d "%~dp0"

:loop
echo [Watchdog] client_locker.py ishga tushirilmoqda...
python client_locker.py
set EXITCODE=%ERRORLEVEL%

if %EXITCODE% EQU 0 (
    echo [Watchdog] Dastur toza holatda (kod 0) yopildi — ataylab chiqilgan, qayta ishga tushirilmaydi.
    goto end
)

echo [Watchdog] Dastur kutilmaganda toxtadi (kod %EXITCODE%). 3 soniyadan keyin qayta ishga tushiriladi...
timeout /t 3 /nobreak >nul
goto loop

:end
pause
