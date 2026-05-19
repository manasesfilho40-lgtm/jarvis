import sys
import time
from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication
from ui import JarvisUI

if __name__ == "__main__":
    ui = JarvisUI()
    
    # Sequence of mock logs, volumes, and states to test the UI flow
    mock_events = [
        ("SYS: Sistema Neural Ativo.", "LISTENING", 0.0),
        ("You: Olá Jarvis, o sistema está pronto?", "LISTENING", 0.0),
        ("Jarvis: Sempre pronto, senhor. Todos os subsistemas do Mark XXXIX estão operacionais.", "SPEAKING", 0.7),
        ("SYS: Acessando banco de dados local.", "THINKING", 0.0),
        ("Jarvis: Acesso concluído. O que deseja fazer agora?", "SPEAKING", 0.4),
        ("You: Toque algumas músicas e ative o modo de foco.", "LISTENING", 0.0),
        ("Jarvis: Certamente, senhor. Iniciando sua playlist favorita.", "SPEAKING", 0.95),
        ("SYS: Spotify ativo.", "LISTENING", 0.0)
    ]
    
    event_idx = 0
    
    def run_next_event():
        global event_idx
        if event_idx < len(mock_events):
            log, state, vol = mock_events[event_idx]
            ui.write_log(log)
            ui.set_state(state)
            ui.set_volume(vol)
            event_idx += 1
        else:
            # Loop events or just stay in listening mode
            ui.set_state("LISTENING")
            ui.set_volume(0.0)
            
    # Trigger events every 3 seconds to let visual animations render and shift states
    timer = QTimer()
    timer.timeout.connect(run_next_event)
    timer.start(3000)
    
    # Run the Qt Event Loop
    sys.exit(ui.app.exec())
