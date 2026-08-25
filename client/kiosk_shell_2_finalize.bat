@echo off
REM ================================================================
REM  KIOSK QOBIG'I — 2-QADAM: Yakunlash
REM ================================================================
REM Bu skriptni FAQAT "Kiosk" hisobida turib ishga tushiring (1-QADAM
REM shu hisobga avtomatik kiritgan bo'lishi kerak). Administrator
REM huquqi SHART EMAS — bu faqat joriy hisobga (HKCU) tegishli.
REM ================================================================

if /I not "%USERNAME%"=="Kiosk" (
    echo.
    echo [XATO] Siz "Kiosk" hisobida emassiz ^(joriy: %USERNAME%^).
    echo Bu skriptni FAQAT "Kiosk" hisobiga kirib turib ishga tushiring.
    echo.
    pause
    exit /b 1
)

cd /d "%~dp0"

echo ================================================================
echo   KIOSK QOBIG'I O'RNATISH — 2-QADAM (YAKUNIY)
echo ================================================================
echo.
echo   Joriy papka: %~dp0
echo   Shu qadamdan keyin, "Kiosk" hisobida ODDIY Windows ish stoli
echo   (Explorer, Boshlash tugmasi va h.k.) UMUMAN ko'rinmay qoladi —
echo   to'g'ridan-to'g'ri qulf ekrani chiqadi, hech qanday "yaltirash"
echo   bo'lmaydi.
echo.
echo   MUHIM: agar keyinchalik muammo chiqsa (dastur ishga tushmasa),
echo   Ctrl+Alt+Delete bosib "Sign out" tanlang va asosiy hisobingizga
echo   qayting — bu HAR DOIM ishlaydi.
echo.
set /p CONFIRM="Davom etasizmi? (ha / yoq): "
if /I not "%CONFIRM%"=="ha" (
    echo Bekor qilindi — hech narsa o'zgartirilmadi.
    pause
    exit /b 0
)

reg add "HKCU\Software\Microsoft\Windows NT\CurrentVersion\Winlogon" /v Shell /t REG_SZ /d "wscript.exe \"%~dp0run_hidden.vbs\"" /f >nul

echo.
echo ================================================================
echo   TAYYOR. Kompyuterni qayta ishga tushiring — endi "Kiosk"
echo   hisobida ish stoli umuman ko'rinmaydi, to'g'ridan-to'g'ri
echo   qulf ekrani chiqadi.
echo.
echo   Buni BEKOR QILISH uchun: shu papkadagi
echo   "kiosk_shell_3_undo.bat" faylini ("Kiosk" hisobida turib)
echo   ishga tushiring.
echo ================================================================
pause
