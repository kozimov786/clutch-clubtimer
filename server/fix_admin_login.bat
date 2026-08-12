@echo off
REM Admin login/parolni tiklash — 'admin' foydalanuvchisi bo'lmasa yaratadi,
REM bo'lsa parolini yangi, ma'lum parolga o'zgartiradi. Joriy parolni
REM bilish shart emas.
cd /d "%~dp0"
..\venv\Scripts\python manage.py fix_admin_login
echo.
pause
