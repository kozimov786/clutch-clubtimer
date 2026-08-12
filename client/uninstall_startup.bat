@echo off
REM Avtomatik ishga tushirishni bekor qilish uchun (Administrator sifatida ishga tushiring).
schtasks /delete /tn "ClutchZoneLocker" /f
echo.
echo Avtomatik ishga tushirish o'chirildi.
pause
