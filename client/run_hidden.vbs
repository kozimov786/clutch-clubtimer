' Windows yoqilganda/tizimga kirilganda Task Scheduler shu faylni chaqiradi.
' Maqsad: update_and_start.bat (git pull -> watchdog.bat -> client_locker.py)
' hech qanday ko'rinadigan konsol oynasisiz (terminal miltillamasdan) ishga
' tushishi — mijoz Windows ish stolini yoki terminalni umuman ko'rmasligi
' kerak, to'g'ridan-to'g'ri kiosk ekrani ochilishi kerak.
Dim fso, shell, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir
' 3-parametr (0) = oyna yashirin; 4-parametr (False) = kutmasdan davom etish
shell.Run """" & scriptDir & "\update_and_start.bat""", 0, False
