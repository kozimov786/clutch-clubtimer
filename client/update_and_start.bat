@echo off
REM Ctrl+Shift+P orqali kiosk rejimidan chiqilgandan keyin — shu faylni
REM ISHGA TUSHIRISH kifoya: avval eng so'nggi kodni serverdan (GitHub)
REM tortib oladi, keyin kiosk rejimini (watchdog bilan, xato bo'lsa
REM avtomatik qayta ishga tushiradigan) qayta ishga tushiradi.
REM
REM Bitta tugma bilan ishlatish uchun: shu faylga o'ng tugma bosib
REM "Send to -> Desktop (create shortcut)" tanlang — Desktop'da paydo
REM bo'lgan yorliqni istasangiz nomini o'zgartiring (masalan "Ishga
REM tushirish"), shundan keyin xodim shu ikonkani ikki marta bosishi
REM kifoya bo'ladi.
cd /d "%~dp0"

echo ================================================================
echo  Clutch Zone — yangilanish va ishga tushirish
echo ================================================================
echo.
echo [1/2] Eng so'nggi kod yuklanmoqda (git pull)...
git pull
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [OGOHLANTIRISH] git pull muvaffaqiyatsiz tugadi ^(masalan internet
    echo yo'q yoki server ishlamayapti^). Kompyuterdagi MAVJUD kod bilan
    echo davom etiladi.
    timeout /t 3 /nobreak >nul
)

echo.
echo [2/2] Kiosk rejimi ishga tushirilmoqda...
echo.
call watchdog.bat
