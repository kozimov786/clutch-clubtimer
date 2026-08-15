@echo off
REM ================================================================
REM  CLUTCH ZONE — YANGI KOMPYUTERNI SOZLASH (BIR TUGMA)
REM ================================================================
REM Bu faylni faqat IKKI MARTA BOSING (Python o'rnatilgandan keyin).
REM O'zi avtomatik: Administrator huquqini so'raydi, kerakli
REM kutubxonalarni o'rnatadi, bu kompyuter uchun config.json'ni
REM sozlaydi va Windows yonganda avtomatik ishga tushishni yoqadi.
REM
REM OLDIN QILISH KERAK: python.org saytidan Python 3.11+ ni
REM o'rnating — o'rnatish oynasida pastdagi "Add python.exe to PATH"
REM belgisini albatta belgilang.
REM ================================================================

REM --- Administrator huquqi kerak (Task Scheduler uchun) ---
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator huquqi so'ralmoqda...
    powershell -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

cd /d "%~dp0"
title Clutch Zone — Yangi kompyuterni sozlash

echo ================================================================
echo   CLUTCH ZONE — YANGI KOMPYUTERNI SOZLASH
echo ================================================================
echo.

REM --- 1. Python borligini tekshirish ---
python --version >nul 2>&1
if errorlevel 1 (
    echo [XATO] Python topilmadi!
    echo.
    echo Avval python.org saytidan Python 3.11 yoki undan yangisini
    echo o'rnating ^("Add python.exe to PATH" belgisini albatta
    echo belgilang^), keyin shu faylni qayta ikki marta bosing.
    echo.
    pause
    exit /b 1
)
echo [1/4] Python topildi.

REM --- 2. Kutubxonalarni o'rnatish ---
echo [2/4] Kerakli kutubxonalar o'rnatilmoqda ^(biroz vaqt olishi mumkin^)...
python -m pip install --disable-pip-version-check -q -r requirements.txt
if errorlevel 1 (
    echo.
    echo [OGOHLANTIRISH] Ba'zi kutubxonalarni o'rnatishda muammo bo'ldi.
    echo Internet aloqasini tekshirib, shu faylni qayta ishga tushiring.
    echo.
    pause
    exit /b 1
)

REM --- 3. Bu kompyuter uchun config.json sozlash ---
echo.
echo [3/4] Bu kompyuter QAYSI stansiya ekanini kiriting.
echo        ^(Masalan: PC-12^)
set /p PCNAME="PC nomi: "
if "%PCNAME%"=="" (
    echo Hech narsa kiritilmadi, "PC-01" ishlatiladi.
    set PCNAME=PC-01
)

python -c "import regenerate_config as r; r.PC_NAME=r'%PCNAME%'; r.main()"
if errorlevel 1 (
    echo.
    echo [XATO] config.json sozlanmadi. regenerate_config.py faylini tekshiring.
    pause
    exit /b 1
)
echo        config.json tayyor ^(PC nomi: %PCNAME%^).

REM --- 4. Windows yonganda avtomatik ishga tushirishni yoqish ---
echo.
echo [4/4] Windows yonganda avtomatik ishga tushirish yoqilmoqda...
schtasks /create /tn "ClutchZoneLocker" /tr "wscript.exe \"%~dp0run_hidden.vbs\"" /sc onlogon /rl highest /f >nul

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ================================================================
    echo   TAYYOR!
    echo ================================================================
    echo   Bu kompyuter endi "%PCNAME%" nomi bilan ishlaydi.
    echo   Kompyuterni qayta yoqing — kiosk ekrani avtomatik ochiladi.
    echo.
    echo   MUHIM: agar bu kompyuterda o'yinlar boshqa D:\ papkada
    echo   o'rnatilgan bo'lsa, regenerate_config.py faylini ochib,
    echo   FALLBACK_GAMES ro'yxatidagi yo'llarni to'g'irlang, so'ng
    echo   shu faylni qayta ishga tushiring.
    echo ================================================================
) else (
    echo.
    echo [XATO] Avtomatik ishga tushirish yoqilmadi. Qayta urinib ko'ring.
)

echo.
pause
