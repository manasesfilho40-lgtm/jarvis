import time
import re
from plyer import notification
import threading

# Keywords definition — matched as whole words only
INTEREST_PATTERNS = [r"\baceito\b", r"\btopo\b", r"\bfechado\b", r"\bquero\b", r"\bfechar\b"]
REJECTION_PATTERNS = [r"\bcaro\b", r"\bdesisti\b", r"\bsem interesse\b", r"\bnão tenho interesse\b", r"\bnão quero\b", r"\bnão obrigado\b", r"\bnão obrigada\b"]

def play_alert_sound():
    try:
        import sys
        if sys.platform == "win32":
            import winsound
            winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
    except Exception:
        pass

def send_notification(title, message):
    try:
        notification.notify(
            title=title,
            message=message,
            app_name="JARVIS Mark XXXIX",
            timeout=10
        )
        play_alert_sound()
    except Exception as e:
        print(f"[Notifier] Error sending notification: {e}")

def _matches_any(text, patterns):
    return any(re.search(p, text) for p in patterns)

def notify_client_reply(message_text):
    message_text_lower = message_text.lower()

    # Check for rejection FIRST (higher priority — avoid false interest on price objections)
    if _matches_any(message_text_lower, REJECTION_PATTERNS):
        send_notification("[!] OBJECAO DETECTADA", f"O cliente apresentou uma objeção: {message_text[:50]}...")
        return

    # Check for interest
    if _matches_any(message_text_lower, INTEREST_PATTERNS):
        send_notification("[!] ALERTA DE INTERESSE", f"O cliente demonstrou alto interesse: {message_text[:50]}...")
        return

    # Default reply notification
    send_notification("[*] Nova Mensagem", f"O cliente respondeu: {message_text[:50]}...")

def monitor_stalled_conversation(last_msg_time, threshold_minutes=30):
    """
    Background check for stalled conversations.
    last_msg_time: float timestamp or list[float] for mutable reference (updated externally).
    """
    def check():
        while True:
            last_time = last_msg_time[0] if isinstance(last_msg_time, list) else last_msg_time
            elapsed = (time.time() - last_time) / 60
            if elapsed > threshold_minutes:
                send_notification("[!] Conversa Parada", f"A conversa está sem resposta há {int(elapsed)} minutos.")
                break
            time.sleep(60)

    threading.Thread(target=check, daemon=True).start()
