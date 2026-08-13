@echo off
REM Bu faylni "Administrator sifatida ishga tushirish" (Run as administrator)
REM orqali BIR MARTA ishga tushiring. Shundan keyin update_and_start.bat
REM kompyuter yoqilganda/foydalanuvchi tizimga kirganda avtomatik ishga
REM tushadi — avval eng so'nggi kodni (git pull) tortib oladi, keyin
REM kiosk rejimini (watchdog bilan) boshlaydi.
cd /d "%~dp0"

schtasks /create /tn "ClutchZoneLocker" /tr "\"%~dp0update_and_start.bat\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo O'RNATILDI: "ClutchZoneLocker" vazifasi Task Scheduler'ga qo'shildi.
    echo Endi kompyuter yoqilganda/tizimga kirilganda avval eng so'nggi kod
    echo yuklanadi ^(git pull^), keyin kiosk rejimi avtomatik ishga tushadi.
) else (
    echo.
    echo XATO: vazifa qo'shilmadi. Bu faylni "Administrator sifatida ishga tushirish" orqali qayta urinib ko'ring.
)
pause
