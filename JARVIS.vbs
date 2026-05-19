Set WshShell = CreateObject("WScript.Shell")
baseDir = "c:\Users\T-GAMER\Documents\Downloads\Mark-XXXIX-main\Mark-XXXIX-main"
WshShell.CurrentDirectory = baseDir
pythonExe = "C:\Users\T-GAMER\AppData\Local\Programs\Python\Python312\pythonw.exe"

' 1. Abre o Jarvis Visivel IMEDIATAMENTE
WshShell.Run """" & pythonExe & """ main.py", 1, False

' 2. Espera um pouco para garantir o foco e roda as acoes de fundo (Spotify)
WScript.Sleep 1500
WshShell.Run """" & pythonExe & """ startup_actions.py", 0, False

Set WshShell = Nothing
