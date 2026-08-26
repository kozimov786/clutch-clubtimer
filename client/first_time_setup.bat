@echo off
REM ================================================================
REM  BIRINCHI MARTA SOZLASH — yangi kompyuter uchun
REM ================================================================
REM OLDINDAN TALAB QILINADI (qo'lda o'rnatiladi):
REM   1. Git — https://git-scm.com
REM   2. Python — https://python.org
REM      O'rnatishda ikkalasini ham BELGILANG:
REM        - "Add python.exe to PATH"
REM        - "Install for all users" (Customize installation ->
REM          Advanced Options) — aks holda faqat shu hisobda ishlaydi,
REM          boshqa hisobda (masalan "Kiosk") Python topilmaydi.
REM
REM Bu ikkitasi o'rnatilgach, repo'ni klonlab, shu faylni
REM "client" papkasi ichida ikki marta bosing — QOLGANINI O'ZI QILADI:
REM kutubxonalarni o'rnatadi, config.json'ni namunadan yaratadi, va
REM PC nomini so'rab, faylga yozadi.
REM ================================================================
cd /d "%~dp0"

where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [XATO] Python topilmadi. Avval python.org'dan o'rnating
    echo ^("Add python.exe to PATH" katakchasini albatta belgilang^).
    pause
    exit /b 1
)

where git >nul 2>&1
if %errorlevel% neq 0 (
    echo [XATO] Git topilmadi. Avval git-scm.com'dan o'rnating.
    pause
    exit /b 1
)

echo ================================================================
echo   CLUTCH ZONE — BIRINCHI MARTA SOZLASH
echo ================================================================
echo.
echo [1/4] Kerakli kutubxonalar o'rnatilmoqda ^(bir necha daqiqa
echo       ketishi mumkin^)...
python -m pip install --upgrade pip >nul 2>&1
python -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo [XATO] Kutubxonalarni o'rnatishda muammo bo'ldi. Yuqoridagi
    echo xato xabarini tekshiring ^(internet aloqasi bormi?^).
    pause
    exit /b 1
)

echo.
if not exist "config.json" (
    echo [2/4] config.json namunadan ^(config.example.json^) yaratilmoqda...
    copy config.example.json config.json >nul
) else (
    echo [2/4] config.json allaqachon mavjud — o'tkazib yuborildi
    echo       ^(agar qayta yaratmoqchi bo'lsangiz, avval eski
    echo       config.json faylini o'chiring^).
)

echo.
set /p PCNAME="[3/4] Shu kompyuterning nomini kiriting (masalan PC-05): "
if "%PCNAME%"=="" (
    echo Bo'sh bo'lishi mumkin emas. Qaytadan ishga tushiring.
    pause
    exit /b 1
)

python -c "import json; p='config.json'; cfg=json.load(open(p, encoding='utf-8')); cfg['pc_name']='%PCNAME%'; json.dump(cfg, open(p, 'w', encoding='utf-8'), indent=2, ensure_ascii=False); print('config.json yangilandi.')"
if %errorlevel% neq 0 (
    echo [XATO] config.json'ni yangilashda muammo bo'ldi.
    pause
    exit /b 1
)

echo.
echo [4/4] Tayyor! PC nomi "%PCNAME%" deb o'rnatildi.
echo.
echo ================================================================
echo   SOZLASH TUGADI.
echo.
echo   Diqqat: config.json ichidagi "server_url" va "websocket_url"
echo   qiymatlari haqiqiy server manzilingizga mos ekanligini
echo   tekshiring (standart: http://192.168.88.100:8001).
echo.
echo   Endi "update_and_start.bat" faylini ishga tushiring.
echo ================================================================
pause
