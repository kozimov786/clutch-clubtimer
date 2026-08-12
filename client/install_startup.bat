@echo off
REM Bu faylni "Administrator sifatida ishga tushirish" (Run as administrator)
REM orqali BIR MARTA ishga tushiring. Shundan keyin watchdog.bat kompyuter
REM yoqilganda/foydalanuvchi tizimga kirganda avtomatik ishga tushadi.
cd /d "%~dp0"

schtasks /create /tn "ClutchZoneLocker" /tr "\"%~dp0watchdog.bat\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo O'RNATILDI: "ClutchZoneLocker" vazifasi Task Scheduler'ga qo'shildi.
    echo Endi kompyuter yoqilganda/tizimga kirilganda watchdog.bat avtomatik ishga tushadi.
) else (
    echo.
    echo XATO: vazifa qo'shilmadi. Bu faylni "Administrator sifatida ishga tushirish" orqali qayta urinib ko'ring.
)
pause
