import time
from plyer import notification
import winsound
import threading

# Keywords definition
INTEREST_KEYWORDS = ["quanto", "aceito", "topo", "fechado", "quero", "preço", "valor"]
REJECTION_KEYWORDS = ["caro", "depois", "não", "desisti", "caro", "agora não"]

def play_alert_sound():
    try:
        # Standard Windows alert sound
        winsound.PlaySound("SystemAsterisk", winsound.SND_ALIAS)
    except:
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

def notify_client_reply(message_text):
    message_text_lower = message_text.lower()
    
    # Check for interest
    if any(kw in message_text_lower for kw in INTEREST_KEYWORDS):
        send_notification("🔥 ALERTA DE INTERESSE", f"O cliente demonstrou alto interesse: {message_text[:50]}...")
        return

    # Check for rejection
    if any(kw in message_text_lower for kw in REJECTION_KEYWORDS):
        send_notification("⚠️ OBJEÇÃO DETECTADA", f"O cliente apresentou uma objeção: {message_text[:50]}...")
        return

    # Default reply notification
    send_notification("💬 Nova Mensagem", f"O cliente respondeu: {message_text[:50]}...")

def monitor_stalled_conversation(last_msg_time, threshold_minutes=30):
    """
    Background check for stalled conversations.
    """
    def check():
        while True:
            elapsed = (time.time() - last_msg_time) / 60
            if elapsed > threshold_minutes:
                send_notification("⏳ Conversa Parada", f"A conversa está sem resposta há {int(elapsed)} minutos.")
                break
            time.sleep(60)
            
    threading.Thread(target=check, daemon=True).start()
