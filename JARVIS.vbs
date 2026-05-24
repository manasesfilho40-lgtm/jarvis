Set WshShell = CreateObject("WScript.Shell")
baseDir = "c:\Users\T-GAMER\Documents\Downloads\Mark-XXXIX-main\Mark-XXXIX-main"
WshShell.CurrentDirectory = baseDir
pythonExe = "C:\Users\T-GAMER\AppData\Local\Programs\Python\Python312\pythonw.exe"

' Abre o Jarvis
WshShell.Run """" & pythonExe & """ main.py", 1, False

Set WshShell = Nothing
