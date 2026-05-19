"""
Instalador do JARVIS Startup
============================
Cria um atalho no Windows Startup para o background_listener.py
"""

import os
import sys
from pathlib import Path
import winshell
from win32com.client import Dispatch

def install_startup():
    base_dir = Path(__file__).resolve().parent
    target_script = base_dir / "actions" / "background_listener.py"
    python_exe = sys.executable
    
    # Caminho da pasta de inicialização do Windows
    startup_path = Path(winshell.startup())
    shortcut_path = startup_path / "JarvisBackgroundListener.lnk"
    
    # Criar o atalho
    shell = Dispatch('WScript.Shell')
    shortcut = shell.CreateShortCut(str(shortcut_path))
    # Argumentos para rodar o script sem console (pythonw)
    shortcut.Targetpath = python_exe.replace("python.exe", "pythonw.exe")
    shortcut.Arguments = f'"{target_script}"'
    shortcut.WorkingDirectory = str(base_dir)
    shortcut.IconLocation = python_exe # Usa o ícone do python
    shortcut.Description = "Escuta palmas para ligar o JARVIS"
    shortcut.save()
    
    print(f"Atalho criado com sucesso em: {shortcut_path}")
    print("Agora o JARVIS ficara de guarda toda vez que voce ligar o PC.")

if __name__ == "__main__":
    install_startup()
