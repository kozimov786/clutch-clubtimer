@echo off
REM Ctrl+Shift+P orqali kiosk rejimidan chiqilgandan keyin — shu faylni
REM ISHGA TUSHIRISH kifoya: kiosk rejimini (watchdog bilan, xato bo'lsa
REM avtomatik qayta ishga tushiradigan) DARHOL ishga tushiradi, so'ngra
REM eng so'nggi kodni (git pull) FON rejimida tortadi.
REM
REM MUHIM: avval bu ikkalasi KETMA-KET edi — avval git pull tugashini
REM (internet sekin bo'lsa bir necha soniya) kutib, keyingina locker
REM ishga tushar edi. Shu orada foydalanuvchi Windows ish stolini
REM ko'rib turar edi. Endi locker QAT'IY birinchi (kutmasdan) ishga
REM tushadi; git pull esa parallel ravishda bajariladi — yangi kod
REM shu zahoti emas, keyingi qayta ishga tushirilishda (watchdog xato
REM tufayli qayta boshlasa yoki kompyuter qayta yoqilsa) qo'llaniladi.
REM
REM Bitta tugma bilan ishlatish uchun: shu faylga o'ng tugma bosib
REM "Send to -> Desktop (create shortcut)" tanlang — Desktop'da paydo
REM bo'lgan yorliqni istasangiz nomini o'zgartiring (masalan "Ishga
REM tushirish"), shundan keyin xodim shu ikonkani ikki marta bosishi
REM kifoya bo'ladi.
cd /d "%~dp0"

REM /B — yangi (ko'rinadigan) oyna ochmasdan, fon jarayoni sifatida
start "" /B watchdog.bat

git pull >nul 2>&1
