@echo off
REM Bu faylni "Administrator sifatida ishga tushirish" (Run as administrator)
REM orqali BIR MARTA ishga tushiring. Shundan keyin watchdog_server.bat
REM kompyuter yoqilganda/tizimga kirilganda avtomatik ishga tushadi —
REM kassa noutbuk qayta yoqilsa ham, server qo'lda ishga tushirish
REM shart bo'lmaydi.
cd /d "%~dp0"

schtasks /create /tn "ClutchZoneServer" /tr "\"%~dp0watchdog_server.bat\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo O'RNATILDI: "ClutchZoneServer" vazifasi Task Scheduler'ga qo'shildi.
    echo Endi kompyuter yoqilganda/tizimga kirilganda server avtomatik ishga tushadi.
) else (
    echo.
    echo XATO: vazifa qo'shilmadi. Bu faylni "Administrator sifatida ishga tushirish" orqali qayta urinib ko'ring.
)
pause
