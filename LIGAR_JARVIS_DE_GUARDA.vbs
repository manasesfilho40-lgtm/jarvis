Set WshShell = CreateObject("WScript.Shell")
baseDir = "c:\Users\T-GAMER\Documents\Downloads\Mark-XXXIX-main\Mark-XXXIX-main"
WshShell.CurrentDirectory = baseDir
pythonExe = "C:\Users\T-GAMER\AppData\Local\Programs\Python\Python312\pythonw.exe"
' Usando pythonw.exe para rodar solto e não fechar quando você fechar o editor
WshShell.Run """" & pythonExe & """ actions/background_listener.py", 0, False
Set WshShell = Nothing
