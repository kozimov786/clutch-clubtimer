@echo off
REM Bu faylni "Administrator sifatida ishga tushirish" (Run as administrator)
REM orqali BIR MARTA ishga tushiring. Shundan keyin kompyuter yoqilganda/
REM foydalanuvchi tizimga kirganda avtomatik ishga tushadi — avval eng
REM so'nggi kodni (git pull) tortib oladi, keyin kiosk rejimini (watchdog
REM bilan) boshlaydi. run_hidden.vbs orqali chaqiriladi — shu tufayli
REM mijoz Windows ish stolini yoki terminal oynasini bir zumga ham
REM ko'rmaydi, to'g'ridan-to'g'ri kiosk ekrani ochiladi.
cd /d "%~dp0"

schtasks /create /tn "ClutchZoneLocker" /tr "wscript.exe \"%~dp0run_hidden.vbs\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo O'RNATILDI: "ClutchZoneLocker" vazifasi Task Scheduler'ga qo'shildi.
    echo Endi kompyuter yoqilganda/tizimga kirilganda avval eng so'nggi kod
    echo yuklanadi ^(git pull^), keyin kiosk rejimi hech qanday oyna
    echo ko'rsatmasdan avtomatik ishga tushadi.
) else (
    echo.
    echo XATO: vazifa qo'shilmadi. Bu faylni "Administrator sifatida ishga tushirish" orqali qayta urinib ko'ring.
)
pause
