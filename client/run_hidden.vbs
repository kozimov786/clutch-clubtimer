' Windows yoqilganda/tizimga kirilganda Task Scheduler (yoki Kiosk
' qobig'i sifatida - Winlogon\Shell) shu faylni chaqiradi.
' Maqsad: update_and_start.bat (git pull -> watchdog.bat -> client_locker.py)
' hech qanday ko'rinadigan konsol oynasisiz (terminal miltillamasdan) ishga
' tushishi — mijoz Windows ish stolini yoki terminalni umuman ko'rmasligi
' kerak, to'g'ridan-to'g'ri kiosk ekrani ochilishi kerak.
'
' MUHIM: 4-parametr TRUE (kutish) bo'lishi SHART. update_and_start.bat
' ichidagi watchdog.bat cheksiz tsikl (hech qachon tugamaydi) — shuning
' uchun bu shell.Run() ham amalda hech qachon qaytmaydi, ya'ni WSCRIPT.EXE
' jarayoni butun sessiya davomida "tirik" qoladi. Bu KIOSK QOBIG'I (Shell)
' sifatida ishlatilganda SHART: agar bu jarayon erta tugasa, Windows
' sessiyani "tugadi" deb hisoblab, ekranni bo'sh/qorong'i qoldirishi yoki
' foydalanuvchini chiqarib yuborishi mumkin edi.
Dim fso, shell, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir
' 3-parametr (0) = oyna yashirin; 4-parametr (True) = tugashini kutish
shell.Run """" & scriptDir & "\update_and_start.bat""", 0, True
