@echo off
REM ================================================================
REM  KIOSK QOBIG'I — BEKOR QILISH (istalgan vaqtda ishlatsa bo'ladi)
REM ================================================================
REM Bu skript ikkala holatda ham ishlaydi:
REM   A) "Kiosk" hisobida turib ishga tushirilsa (masalan uning
REM      ish stoliga biror yorliq orqali kirib olsangiz) — o'zining
REM      qobig'ini to'g'ridan-to'g'ri tozalaydi.
REM   B) Boshqa (masalan Administrator) hisobda turib, "Kiosk"
REM      HOZIR TIZIMGA KIRMAGAN paytda ishga tushirilsa — "Kiosk"
REM      profilini vaqtincha yuklab (offline), o'sha yerdan
REM      tozalaydi. Bu holatda Administrator huquqi SHART.
REM ================================================================
cd /d "%~dp0"

if /I "%USERNAME%"=="Kiosk" (
    echo ["Kiosk" hisobi ichida] Qobiq sozlamasi tozalanmoqda...
    reg delete "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /f
    echo.
    echo TAYYOR. Kompyuterni qayta ishga tushiring — "Kiosk" hisobida
    echo endi yana oddiy Windows ish stoli chiqadi.
    pause
    exit /b 0
)

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Siz "Kiosk" hisobida emassiz — bu holatda Administrator
    echo huquqi kerak. Fayl ustiga o'ng tugma bosib "Run as
    echo administrator" tanlang.
    pause
    exit /b 1
)

if not exist "C:\Users\Kiosk\NTUSER.DAT" (
    echo "Kiosk" profili topilmadi ^(C:\Users\Kiosk\NTUSER.DAT^).
    echo Agar hisob boshqa joyda bo'lsa, shu faylni qo'lda tahrirlab,
    echo yo'lni to'g'irlang.
    pause
    exit /b 1
)

echo ["Kiosk" hisobi HOZIR tizimga kirmagan deb faraz qilinmoqda]
echo "Kiosk" profili vaqtincha yuklanmoqda...
reg load "HKU\ClutchKioskTemp" "C:\Users\Kiosk\NTUSER.DAT"
if %ERRORLEVEL% NEQ 0 (
    echo [XATO] Profilni yuklab bo'lmadi — "Kiosk" hisobi hozir
    echo tizimga kirgan bo'lishi mumkin ^(shunday bo'lsa, avval undan
    echo chiqing: Ctrl+Alt+Delete -^> Sign out^), keyin qayta urinib
    echo ko'ring.
    pause
    exit /b 1
)

reg delete "HKU\ClutchKioskTemp\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /f
reg unload "HKU\ClutchKioskTemp"

echo.
echo TAYYOR. "Kiosk" hisobi qobig'i tozalandi — keyingi safar unga
echo kirilganda oddiy Windows ish stoli chiqadi.
echo.
echo Agar avtomatik kirishni ham to'liq o'chirmoqchi bo'lsangiz:
echo reg delete "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /f
pause
