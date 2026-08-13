@echo off
REM Bu faylni "Administrator sifatida ishga tushirish" (Run as administrator)
REM orqali BIR MARTA ishga tushiring. Shundan keyin kompyuter yoqilganda/
REM tizimga kirilganda server avtomatik ishga tushadi — avval eng so'nggi
REM kodni (git pull) tortib oladi, keyin Daphne'ni (watchdog bilan)
REM boshlaydi. run_hidden.vbs orqali chaqiriladi — hech qanday terminal
REM oynasi ko'rinmaydi.
cd /d "%~dp0"

schtasks /create /tn "ClutchZoneServer" /tr "wscript.exe \"%~dp0run_hidden.vbs\"" /sc onlogon /rl highest /f

if %ERRORLEVEL% EQU 0 (
    echo.
    echo O'RNATILDI: "ClutchZoneServer" vazifasi Task Scheduler'ga qo'shildi.
    echo Endi kompyuter yoqilganda/tizimga kirilganda server avval eng
    echo so'nggi kodni yuklab ^(git pull^), keyin hech qanday oyna
    echo ko'rsatmasdan avtomatik ishga tushadi.
) else (
    echo.
    echo XATO: vazifa qo'shilmadi. Bu faylni "Administrator sifatida ishga tushirish" orqali qayta urinib ko'ring.
)
pause
