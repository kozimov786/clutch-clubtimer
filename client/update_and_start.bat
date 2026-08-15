@echo off
REM Ctrl+Shift+P orqali kiosk rejimidan chiqilgandan keyin — shu faylni
REM ISHGA TUSHIRISH kifoya: kiosk rejimini (watchdog bilan, xato bo'lsa
REM avtomatik qayta ishga tushiradigan) DARHOL ishga tushiradi, so'ngra
REM eng so'nggi kodni (git pull) FON rejimida tortadi.
REM
REM MUHIM (2-marta topilgan xato): birinchi urinishda bu teskarisi
REM qilingan edi — watchdog.bat FON rejimiga ("start /B") olinib, git
REM pull esa asosiy oqimda qolgan edi. Bu esa client'ni kompyuter
REM qayta yoqilganda UMUMAN ishga tushmay qolishiga sabab bo'ldi:
REM git pull tugagach, shu skriptning o'zi (uni chaqirgan yashirin
REM konsol) tugab, YOPILIB ketardi — va o'sha konsolga hali ham
REM "biriktirilgan" fondagi watchdog.bat/client_locker.py zanjiri ham
REM konsol yopilishi bilan birga to'xtab/yo'q qilinishi mumkin edi.
REM
REM TO'G'RI YECHIM: buning aksi — git pull FON rejimiga ("start /B")
REM olinadi (u tezkor va muhim emas), watchdog.bat esa "call" bilan,
REM ASOSIY oqimda, CHEKSIZ tsikl sifatida qoladi — aynan shu "call"
REM shu skriptni (demak, uni ishga tushirgan yashirin konsolni) butun
REM kiosk sessiyasi davomida TIRIK ushlab turadi, hech narsa erta
REM yopilib qolmaydi. locker esa hamon DARHOL (git pull tugashini
REM kutmasdan) ishga tushadi, chunki ikkalasi PARALLEL boshlanadi.
cd /d "%~dp0"

start "" /B git pull

call watchdog.bat
