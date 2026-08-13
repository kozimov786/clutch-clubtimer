@echo off
REM Kassa noutbukda serverni qayta ishga tushirish uchun BITTA fayl:
REM avval eng so'nggi kodni (git pull) tortib oladi, keyin serverni
REM (watchdog bilan, kutilmagan to'xtashda o'zi qayta ishga tushiradigan)
REM ishga tushiradi. migrate start_server.bat ichida avtomatik bajariladi.
REM
REM Bitta tugma bilan ishlatish uchun: shu faylga o'ng tugma bosib
REM "Send to -> Desktop (create shortcut)" tanlang.
cd /d "%~dp0"

echo ================================================================
echo  Clutch Zone Server — yangilanish va ishga tushirish
echo ================================================================
echo.
echo [1/2] Eng so'nggi kod yuklanmoqda (git pull)...
git pull
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [OGOHLANTIRISH] git pull muvaffaqiyatsiz tugadi ^(masalan internet
    echo yo'q^). Kompyuterdagi MAVJUD kod bilan davom etiladi.
    timeout /t 3 /nobreak >nul
)

echo.
echo [2/2] Server ishga tushirilmoqda...
echo.
call watchdog_server.bat
