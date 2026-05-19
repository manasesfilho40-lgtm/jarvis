"""
Background Listener for JARVIS
==============================
This script runs in the background (no window) and waits for a double-clap
to launch the main JARVIS application.

It is designed to be added to Windows Startup.
"""

import io
import os
import subprocess
import sys
import time
import psutil
from pathlib import Path

# Fix Windows console encoding
if sys.platform == "win32":
    try:
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
        os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    except Exception:
        pass

# Adiciona o diretório raiz ao path para importar o detector
base_dir = Path(__file__).resolve().parent.parent
sys.path.append(str(base_dir))

from actions.clap_detector import ClapDetector

MAIN_SCRIPT = base_dir / "main.py"
PYTHON_EXE = sys.executable
detector = None # Variável global para o detector

def is_jarvis_running():
    """Verifica se o main.py já está rodando."""
    for proc in psutil.process_iter(['cmdline', 'name']):
        try:
            cmdline = proc.info.get('cmdline')
            name = proc.info.get('name')
            if cmdline and name and "python" in name.lower():
                cmd_str = " ".join(cmdline)
                if "main.py" in cmd_str and "background_listener.py" not in cmd_str:
                    return True
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False

def launch_jarvis():
    """Lança o JARVIS se não estiver rodando."""
    if is_jarvis_running():
        print("[Background] JARVIS já está em execução.")
        return

    detector._log("[Background] Lançando JARVIS via VBS...")
    try:
        vbs_path = base_dir / "JARVIS.vbs"
        os.startfile(str(vbs_path))
        detector._log("[Background] Comando de lançamento enviado.")
    except Exception as e:
        detector._log(f"[Background] Erro ao lançar: {e}")

def on_claps_detected():
    if detector:
        detector._log("[Background] 👏 Palmas detectadas! Tentando abrir o Jarvis...")
    launch_jarvis()

def start_background_listener():
    print("[Background] Ouvinte de fundo ativado. Aguardando palmas...")
    # Sensibilidade equilibrada (0.02) para capturar palmas naturais
    global detector
    detector = ClapDetector(on_clap=on_claps_detected, threshold=0.02)
    
    try:
        while True:
            jarvis_active = is_jarvis_running()
            if jarvis_active and detector._running:
                detector._log("[Background] JARVIS em execução. Desativando escuta temporariamente para evitar conflitos.")
                detector.stop()
            elif not jarvis_active and not detector._running:
                detector._log("[Background] JARVIS não está rodando. Ativando escuta...")
                detector.start()
            time.sleep(2)
    except KeyboardInterrupt:
        detector.stop()

if __name__ == "__main__":
    start_background_listener()
