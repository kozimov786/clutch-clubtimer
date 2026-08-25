@echo off
REM ================================================================
REM  KIOSK QOBIG'I — 1-QADAM: "Kiosk" hisobini yaratish
REM ================================================================
REM MAQSAD: Windows ish stoli hech qachon "yaltiramasligi" uchun
REM (Professional kiosk/bankomat/POS tizimlarida ishlatiladigan
REM standart usul) — dasturimiz Windows uchun Explorer.exe'ning
REM O'RNINI BOSADI, ya'ni oddiy ish stoli umuman ishga tushmaydi.
REM
REM XAVFSIZLIK: bu ALOHIDA, CHEKLANGAN "Kiosk" hisobida qilinadi —
REM sizning asosiy (Administrator) hisobingizga HECH QANDAY ta'sir
REM qilmaydi. Muammo chiqsa: Ctrl+Alt+Delete bosing -> "Sign out" ->
REM asosiy hisobingizga kiring (pastga, "MUHIM" qismiga qarang).
REM
REM ISHLATISH: shu faylni "Administrator sifatida ishga tushirish".
REM ================================================================

net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Administrator huquqi kerak. Fayl ustiga o'ng tugma bosib
    echo "Run as administrator" ^(Administrator sifatida ishga tushirish^) tanlang.
    pause
    exit /b 1
)

cd /d "%~dp0"

echo ================================================================
echo   KIOSK QOBIG'I O'RNATISH — 1-QADAM
echo ================================================================
echo.
echo   Bu skript "Kiosk" nomli YANGI, cheklangan Windows hisobini
echo   yaratadi va uni kompyuter yoqilganda AVTOMATIK kiritadi.
echo   Sizning hozirgi hisobingiz o'zgarishsiz qoladi.
echo.
set /p KIOSK_PASS="Kiosk hisobi uchun parol o'ylab toping (buni eslab qoling): "
if "%KIOSK_PASS%"=="" (
    echo Parol bo'sh bo'lishi mumkin emas.
    pause
    exit /b 1
)

echo.
echo [1/3] "Kiosk" hisobi yaratilmoqda...
net user Kiosk "%KIOSK_PASS%" /add /expires:never
net localgroup Users Kiosk /add >nul 2>&1

echo [2/3] Avtomatik kirish ^(auto-logon^) sozlanmoqda...
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v AutoAdminLogon /t REG_SZ /d 1 /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultUserName /t REG_SZ /d "Kiosk" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultPassword /t REG_SZ /d "%KIOSK_PASS%" /f >nul
reg add "HKLM\SOFTWARE\Microsoft\Windows NT\CurrentVersion\Winlogon" /v DefaultDomainName /t REG_SZ /d "%COMPUTERNAME%" /f >nul

echo [3/3] Tayyor.
echo.
echo ================================================================
echo   1-QADAM BAJARILDI. Endi:
echo ================================================================
echo   1. Kompyuterni QAYTA ISHGA TUSHIRING.
echo   2. Windows avtomatik "Kiosk" hisobiga kiradi — bu safar HALI
echo      ODDIY ish stoli ko'rinadi (bu normal, kutilgan holat).
echo   3. Shu "Kiosk" hisobida turib, ushbu papkadagi
echo      "kiosk_shell_2_finalize.bat" faylini toping va uni
echo      ikki marta bosing (Administrator shart emas).
echo.
echo   MUHIM ^(muammo chiqsa^): kiosk rejimi ishga tushgandan keyin
echo   biror narsa noto'g'ri ketsa — Ctrl+Alt+Delete bosing, "Sign
echo   out" tanlang, va o'zingizning asosiy hisobingizga qayting.
echo   Bu HAR DOIM ishlaydi, hatto ekranda hech narsa ko'rinmasa ham.
echo ================================================================
pause
