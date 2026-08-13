' Windows yoqilganda/tizimga kirilganda Task Scheduler shu faylni chaqiradi.
' Maqsad: update_and_start_server.bat (git pull -> watchdog_server.bat ->
' Daphne) hech qanday ko'rinadigan konsol oynasisiz ishga tushishi.
Dim fso, shell, scriptDir
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
scriptDir = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = scriptDir
' 3-parametr (0) = oyna yashirin; 4-parametr (False) = kutmasdan davom etish
shell.Run """" & scriptDir & "\update_and_start_server.bat""", 0, False
