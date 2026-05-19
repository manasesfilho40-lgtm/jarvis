Set WshShell = CreateObject("WScript.Shell")
baseDir = "c:\Users\T-GAMER\Documents\Downloads\Mark-XXXIX-main\Mark-XXXIX-main"
WshShell.CurrentDirectory = baseDir
pythonExe = "C:\Users\T-GAMER\AppData\Local\Programs\Python\Python312\python.exe"
' Roda o teste por 10 segundos
WshShell.Run """" & pythonExe & """ teste_palma_arquivo.py", 0, True
WshShell.Popup "Teste concluído! Verifique o arquivo resultado_teste.txt", 5, "Jarvis Test"
Set WshShell = Nothing
