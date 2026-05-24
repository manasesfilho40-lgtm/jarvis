import asyncio
import os
import re
import threading
import json
import sys
import traceback
import numpy as np

# Fix Windows console encoding (cp1252 can't handle emojis)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='backslashreplace')
        sys.stderr.reconfigure(encoding='utf-8', errors='backslashreplace')
    except Exception:
        pass

import builtins
def print(*args, **kwargs):
    if sys.stdout is None:
        return
    safe_args = []
    try:
        enc = getattr(sys.stdout, 'encoding', None) or "utf-8"
    except Exception:
        enc = "utf-8"
    for arg in args:
        if isinstance(arg, str):
            try:
                safe_args.append(arg.encode(enc, errors="replace").decode(enc))
            except Exception:
                safe_args.append(arg)
        else:
            safe_args.append(arg)
    try:
        builtins.print(*safe_args, **kwargs)
    except Exception:
        pass


import sounddevice as sd
from google import genai
from google.genai import types
from ui import JarvisUI
from memory.memory_manager import (
    manage_memory, memory
)

from actions.file_processor import file_processor
from actions.flight_finder     import flight_finder
from actions.open_app          import open_app
from actions.weather_report    import weather_action
from actions.send_message      import send_message
from actions.reminder          import reminder
from actions.computer_settings import computer_settings
from actions.screen_processor  import screen_process
from actions.youtube_video     import youtube_video
from actions.desktop           import desktop_control
from actions.browser_control   import browser_control
from actions.file_controller   import file_controller
from actions.code_helper       import code_helper
from actions.dev_agent         import dev_agent
from actions.web_search        import web_search as web_search_action
from actions.computer_control  import computer_control
from actions.game_updater      import game_updater
from actions.clap_detector     import ClapDetector
from actions.apify_leads       import apify_leads
from actions.whatsapp_web     import whatsapp_web_action
from actions.negotiation_script import negotiation_script_action
from actions.geopolitics_monitor import fetch_geopolitics_news
from agent.local_stt import LocalSTT
from plugins.plugin_manager import get_plugin_manager

clap_detector = None

def _run_geopolitics_refresh() -> str:
    """Triggers a geopolitics news refresh and pushes to UI."""
    try:
        news_json = fetch_geopolitics_news()
        ui.update_geopolitics(news_json)
        return "Notícias geopolíticas atualizadas com sucesso."
    except Exception as e:
        return f"Erro ao atualizar notícias: {e}"

from core.utils import BASE_DIR, API_CONFIG_PATH, get_api_key as _get_api_key

PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-3.1-flash-live-preview"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024


def _load_system_prompt() -> str:
    user_facts = memory.get_all()
    try:
        base_prompt = PROMPT_PATH.read_text(encoding="utf-8")
    except Exception:
        base_prompt = (
            "You are JARVIS, Tony Stark's AI assistant. "
            "Be concise, direct, and always use the provided tools to complete tasks. "
            "Never simulate or guess results — always call the appropriate tool."
        )
    
    full_prompt = f"{base_prompt}\n\n[USER PERSONAL INFORMATION & MEMORY]\n{user_facts}\n"
    full_prompt += "\nALWAYS use the Brave browser for any web-related tasks."
    full_prompt += "\nALWAYS respond in Brazilian Portuguese (pt-BR). NUNCA fale inglês."
    full_prompt += "\nNUNCA responda a si mesmo. Só fale quando o USUÁRIO falar com você."
    full_prompt += "\nREGRA CRÍTICA DE SILÊNCIO: Se o áudio do usuário estiver vazio ou contiver apenas ruído, NÃO responda NADA."
    full_prompt += "\nNUNCA invente resultados. Comunique o resultado real retornado pelas tools."
    full_prompt += "\nPERSONALIDADE: Fale de forma polida, leal e formal, como o J.A.R.V.I.S. Trate o usuário como 'senhor'."
    return full_prompt

_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

def _clean_transcript(text: str) -> str:    
    text = _CTRL_RE.sub("", text)
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()

from core.tools_schema import TOOL_DECLARATIONS

class JarvisLive:

    def __init__(self, ui: JarvisUI):
        self.ui             = ui
        self.session        = None
        self.audio_in_queue = None
        self.out_queue      = None
        self._loop          = None
        self._is_speaking   = False
        self._post_speech_cooldown = False
        self._speaking_lock = threading.Lock()
        self.ui.on_text_command = self._on_text_command
        self._turn_done_event: asyncio.Event | None = None
        self._last_text_input = None
        self._night_mode = False
        self._night_mode_schedule = None
        self._local_stt = None

    def _on_text_command(self, text: str):
        # Filtra comandos locais dos cards para evitar que a IA chame ferramentas indevidas
        if text in ("memory status", "show tasks", "show insights"):
            self.ui.write_log(f"SYS: Comando local '{text}' executado.")
            return

        # Model routing control commands
        text_lower = text.lower().strip()
        if text_lower in ("usar cerebro auto", "usar modelo auto", "modo auto", "inteligencia auto"):
            from agent.local_genai import set_routing_mode
            set_routing_mode("auto")
            self.ui.write_log("SYS: Inteligência Híbrida ativada. Llama 3 para tarefas simples, Gemini para complexas.")
            self.ui._push_model_info()
            return

        if text_lower in ("usar cerebro local", "usar cerebro llama", "usar llama", "modo local"):
            from agent.local_genai import set_routing_mode
            set_routing_mode("llama")
            self.ui.write_log("SYS: Cérebro Local ativado. Todas as tarefas rodando offline via Llama 3.")
            self.ui._push_model_info()
            return

        if text_lower in ("usar cerebro gemini", "usar cerebro nuvem", "usar gemini", "modo nuvem"):
            from agent.local_genai import set_routing_mode
            set_routing_mode("gemini")
            self.ui.write_log("SYS: Cérebro na Nuvem ativado. Todas as tarefas rodando via Gemini API.")
            self.ui._push_model_info()
            return

        # Change Ollama model via text: "usar modelo ollama qwen2.5:3b"
        ollama_model_match = re.match(r"usar modelo ollama\s+(\S+)", text_lower)
        if ollama_model_match:
            from agent.local_genai import set_ollama_model
            model_name = ollama_model_match.group(1)
            set_ollama_model(model_name)
            self.ui.write_log(f"SYS: Modelo Ollama alterado para {model_name}")
            self.ui._push_model_info()
            return

        if text == "start lead generation prospecting":
            self.ui.write_log("SYS: Iniciando busca automatizada de leads no Apify...")
            res = apify_leads(parameters={
                "actor_id": "compass/crawler-google-places",
                "input_data": {"searchStringsArray": ["advogados em São Paulo"], "maxResults": 10}
            })
            self.ui.write_log(f"SYS: {res}")
            return

        if text == "stop lead generation prospecting":
            self.ui.write_log("SYS: Busca de leads interrompida.")
            return

        if text == "open whatsapp automation agent":
            self.ui.write_log("SYS: Iniciando assistente de WhatsApp com Playwright/Brave...")
            def _run():
                try:
                    res = whatsapp_web_action({
                        "action": "autonomous",
                        "target": "leads_results",
                        "product": "Criativos de Moda Streetwear"
                    }, player=self.ui)
                    self.ui.write_log(f"SYS: WhatsApp: {res}")
                except Exception as e:
                    self.ui.write_log(f"ERR: {e}")
            threading.Thread(target=_run, daemon=True).start()
            return

        if text == "request_leads_refresh":
            try:
                leads_db_path = BASE_DIR / "config" / "leads_db.json"
                if leads_db_path.exists():
                    with open(leads_db_path, "r", encoding="utf-8") as f:
                        leads_data = f.read()
                        self.ui.update_leads(leads_data)
                else:
                    self.ui.update_leads('{"new":[],"used":[]}')
            except Exception as e:
                print(f"Error reading leads_db.json: {e}")
            return

        if text == "close whatsapp automation agent":
            self.ui.write_log("SYS: Assistente de WhatsApp finalizado.")
            return

        if text == "connect_live_link":
            self.ui.muted = False
            self.ui.set_state("LISTENING")
            self.ui.write_log("SYS: Escuta do Gemini Live ativada.")
            return

        if text == "disconnect_live_link":
            self.ui.muted = True
            self.ui.set_state("MUTED")
            self.ui.write_log("SYS: Escuta do Gemini Live silenciada.")
            return

        if text == "night_mode_on":
            self._night_mode = True
            self.ui.muted = True
            self.ui.set_state("NIGHT_MODE")
            self.ui.write_log("🌙 Modo Noturno ativado. JARVIS em repouso.")
            return

        if text == "night_mode_off":
            self._night_mode = False
            self.ui.muted = False
            self.ui.set_state("LISTENING")
            self.ui.write_log("🌙 Modo Noturno desativado. JARVIS operacional.")
            return
            
        if not self._loop or not self.session:
            from agent.local_genai import get_routing_mode
            mode = get_routing_mode()
            if mode == "gemini":
                brain_desc = "via cérebro na nuvem Gemini"
            elif mode == "llama":
                brain_desc = "via cérebro local Llama 3"
            else:
                brain_desc = "via cérebro híbrido (Gemini/Llama)"
            self.ui.write_log(f"JARVIS: Senhor, o sistema está offline. Executando '{text}' {brain_desc}...")
            from agent.task_queue import get_queue, TaskPriority
            def ui_speak(msg):
                print(f"[JARVIS] 🗣️ {msg}")
                self.ui.write_log(f"JARVIS: {msg}")
                def _run():
                    try:
                        import win32com.client
                        speaker = win32com.client.Dispatch("SAPI.SpVoice")
                        try:
                            for v in speaker.GetVoices():
                                desc = v.GetDescription().lower() if hasattr(v, "GetDescription") else ""
                                lang_id = v.Id.lower() if hasattr(v, "Id") else ""
                                if "language=416" in lang_id or "language=816" in lang_id or "portug" in desc:
                                    speaker.Voice = v
                                    break
                        except Exception as voice_err:
                            print(f"[TTS Voice Selector Warning] {voice_err}")
                        speaker.Speak(msg)
                    except Exception as tts_err:
                        print(f"[TTS Error] {tts_err}")
                threading.Thread(target=_run, daemon=True).start()
            
            get_queue().submit(
                goal=text,
                priority=TaskPriority.HIGH,
                speak=ui_speak
            )
            return
            
        was_muted = self.ui.muted
        self._last_text_input = text
        asyncio.run_coroutine_threadsafe(
            self.session.send(input=text, end_of_turn=True),
            self._loop
        )
        def _restore_mute():
            import time as _t
            _t.sleep(0.3)
            if was_muted:
                self.ui.muted = True
                self.ui.set_state("MUTED")
        threading.Thread(target=_restore_mute, daemon=True).start()

    def _handle_night_mode(self, args: dict) -> str:
        action = args.get("action", "toggle")
        if action == "on":
            self._night_mode = True
            self.ui.muted = True
            self.ui.set_state("NIGHT_MODE")
            self.ui.write_log("🌙 Modo Noturno ativado.")
            return "Modo Noturno ativado. Ficarei em silêncio."
        elif action == "off":
            self._night_mode = False
            self.ui.muted = False
            self.ui.set_state("LISTENING")
            self.ui.write_log("🌙 Modo Noturno desativado.")
            return "Modo Noturno desativado. Estou de volta."
        elif action == "schedule" and args.get("hour") is not None:
            self._night_mode_schedule = (args["hour"], args.get("minute", 0))
            self.ui.write_log(f"🌙 Modo Noturno agendado para {args['hour']:02d}:{args.get('minute',0):02d}.")
            return f"Modo Noturno agendado para {args['hour']:02d}:{args.get('minute',0):02d}."
        return "Ação inválida. Use action='on', 'off' ou 'schedule'."

    def _handle_read_screen(self, args: dict) -> str:
        self.ui.write_log("👁 Lendo a tela...")
        try:
            import mss, pytesseract
            from PIL import Image
            with mss.mss() as sct:
                img = sct.grab(sct.monitors[1])
                pil_img = Image.frombytes("RGB", (img.width, img.height), img.rgb)
                text = pytesseract.image_to_string(pil_img, lang="por")
            if text.strip():
                self.speak(text[:3000])
                return f"Leitura concluída. {len(text)} caracteres encontrados."
            return "Não encontrei texto legível na tela."
        except ImportError:
            return "Preciso do pytesseract e Tesseract OCR instalados para ler a tela."
        except Exception as e:
            return f"Erro ao ler tela: {e}"

    def _handle_proactive_check(self) -> str:
        results = []
        try:
            from core.quota_tracker import get_usage
            from memory.memory_manager import memory
            try:
                with open(API_CONFIG_PATH, "r", encoding="utf-8") as _fk:
                    api_key = json.load(_fk).get("gemini_api_key", "")
                if api_key:
                    quota = get_usage(api_key, "gemini-2.5-flash")
                    if quota["pct"] > 80:
                        results.append(f"⚠ Cota da API em {quota['pct']}%, restam {quota['limit'] - quota['used']} requisições.")
            except Exception:
                pass
            import time
            from datetime import datetime as _dt
            now = _dt.now()
            if self._night_mode_schedule:
                h, m = self._night_mode_schedule
                if now.hour == h and now.minute == m and not self._night_mode:
                    self._night_mode = True
                    self.ui.muted = True
                    self.ui.set_state("NIGHT_MODE")
                    results.append("🌙 Modo Noturno ativado automaticamente.")
                elif now.hour == (h + 7) % 24 and now.minute == m and self._night_mode:
                    self._night_mode = False
                    self.ui.muted = False
                    self.ui.set_state("LISTENING")
                    results.append("🌅 Modo Noturno desativado. Bom dia, senhor.")
        except Exception as e:
            results.append(f"Erro na verificação: {e}")
        return "; ".join(results) if results else "Nada a reportar."

    def set_speaking(self, value: bool):
        global clap_detector
        with self._speaking_lock:
            was_speaking = self._is_speaking
            self._is_speaking = value
        if value:
            self.ui.set_state("SPEAKING")
            # Disable clap detector while speaking to prevent false unmutes
            if clap_detector:
                clap_detector.enabled = False
        else:
            if was_speaking:
                # Cooldown: block mic for 2.5s after Jarvis stops speaking
                self._post_speech_cooldown = True
                import time as _time
                def _clear_cooldown():
                    _time.sleep(2.5)
                    self._post_speech_cooldown = False
                    # Drain any stale audio that leaked in during speech
                    while self.out_queue and not self.out_queue.empty():
                        try:
                            self.out_queue.get_nowait()
                        except Exception:
                            break
                    # Re-enable clap detector after cooldown
                    if clap_detector:
                        clap_detector.enabled = True
                threading.Thread(target=_clear_cooldown, daemon=True).start()
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            else:
                self.ui.set_state("MUTED")

    def speak(self, text: str):
        if not self._loop or not self.session or self.ui.muted:
            return
        async def _send():
            await self.session.send_client_content(
                turns=types.Content(
                    role="model",
                    parts=[types.Part(text=text)]
                ),
                turn_complete=True
            )
        asyncio.run_coroutine_threadsafe(_send(), self._loop)

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
        if not self.ui.muted:
            self.speak(f"Sir, {tool_name} encountered an error. {short}")

    def _build_config(self) -> types.LiveConnectConfig:
        from datetime import datetime

        mem_str    = memory.get_all()
        sys_prompt = _load_system_prompt()

        now      = datetime.now()
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")
        time_ctx = (
            f"[CURRENT DATE & TIME]\n"
            f"Right now it is: {time_str}\n"
            f"Use this to calculate exact times for reminders.\n\n"
        )

        parts = [time_ctx]
        if mem_str:
            parts.append(mem_str)
        parts.append(sys_prompt)

        # Get recent context from Obsidian Conversas.md
        try:
            from memory.obsidian_manager import get_recent_history
            recent_history = get_recent_history(limit=3)
            if recent_history:
                parts.append(f"\n[RECENT CONVERSATION HISTORY]\n{recent_history}\n")
        except Exception as e:
            print(f"[Obsidian Memory Sync Warning] Could not load history: {e}")

        return types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction="\n".join(parts),
            tools=[{"function_declarations": TOOL_DECLARATIONS}],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Charon"
                    )
                )
            ),
        )

    async def _execute_tool(self, fc) -> types.FunctionResponse:
        name = fc.name
        args = dict(fc.args or {})

        print(f"[JARVIS] 🔧 {name}  {args}")
        self.ui.set_state("THINKING")

        if name == "save_memory":
            category = args.get("category", "notes")
            key      = args.get("key", "")
            value    = args.get("value", "")
            if key and value:
                memory.store(f"{category}/{key}", value)
                print(f"[Memory] 💾 save_memory: {category}/{key} = {value}")
            if not self.ui.muted:
                self.ui.set_state("LISTENING")
            return types.FunctionResponse(
                id=fc.id, name=name,
                response={"result": "ok", "silent": True}
            )

        loop   = asyncio.get_event_loop()
        result = "Done."

        def _run_in_new_thread(fn, args, player):
            import threading
            result = [None]
            def _target():
                try:
                    result[0] = fn(parameters=args, player=player)
                except Exception as e:
                    result[0] = f"Error: {e}"
            t = threading.Thread(target=_target, daemon=True)
            t.start()
            return "Task started in background. Check logs for completion."

        try:
            # Dictionary for tools that run in executor
            executor_tools = {
                "manage_memory": lambda: manage_memory(args),
                "open_app": lambda: open_app(parameters=args, response=None, player=self.ui),
                "weather_report": lambda: weather_action(parameters=args, player=self.ui),
                "browser_control": lambda: browser_control(parameters=args, player=self.ui),
                "file_controller": lambda: file_controller(parameters=args, player=self.ui),
                "send_message": lambda: send_message(parameters=args, response=None, player=self.ui, session_memory=None),
                "reminder": lambda: reminder(parameters=args, response=None, player=self.ui),
                "youtube_video": lambda: youtube_video(parameters=args, response=None, player=self.ui),
                "computer_settings": lambda: computer_settings(parameters=args, response=None, player=self.ui),
                "desktop_control": lambda: desktop_control(parameters=args, player=self.ui),
                "code_helper": lambda: code_helper(parameters=args, player=self.ui, speak=self.speak),
                "dev_agent": lambda: dev_agent(parameters=args, player=self.ui, speak=self.speak),
                "web_search": lambda: web_search_action(parameters=args, player=self.ui),
                "file_processor": lambda: file_processor(parameters=args, player=self.ui, speak=self.speak),
                "apify_leads": lambda: apify_leads(parameters=args),
                "computer_control": lambda: computer_control(parameters=args, player=self.ui),
                "game_updater": lambda: game_updater(parameters=args, player=self.ui, speak=self.speak),
                "flight_finder": lambda: flight_finder(parameters=args, player=self.ui),
                "whatsapp_web": lambda: _run_in_new_thread(whatsapp_web_action, args, self.ui),
                "negotiation_script": lambda: negotiation_script_action(parameters=args, player=self.ui),
                "notifier": lambda: __import__("actions.notifier", fromlist=["send_notification"]).send_notification(args.get("title", "Alert"), args.get("message", "")),
                "self_repair": lambda: __import__("actions.self_repair", fromlist=["run_diagnostics_and_repair"]).run_diagnostics_and_repair(args, self.ui, self.speak),
                "manage_crm": lambda: __import__("actions.leads_manager", fromlist=["manage_crm"]).manage_crm(args),
                "refresh_geopolitics": lambda: _run_geopolitics_refresh(),
                "night_mode": lambda: self._handle_night_mode(args),
                "read_screen": lambda: self._handle_read_screen(args),
                "proactive_check": lambda: self._handle_proactive_check()
            }

            if name in executor_tools:
                # Special handling for file_processor to inject current file if missing
                if name == "file_processor" and not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                
                r = await loop.run_in_executor(None, executor_tools[name])
                result = r or "Done."

            elif name == "screen_process":
                await loop.run_in_executor(
                    None, 
                    lambda: screen_process(parameters=args, response=None, player=self.ui, session_memory=None)
                )
                result = "Vision module activated. Stay completely silent — vision module will speak directly."

            elif name == "agent_task":
                from agent.task_queue import get_queue, TaskPriority
                priority_map = {"low": TaskPriority.LOW, "normal": TaskPriority.NORMAL, "high": TaskPriority.HIGH}
                priority = priority_map.get(args.get("priority", "normal").lower(), TaskPriority.NORMAL)
                task_id  = get_queue().submit(goal=args.get("goal", ""), priority=priority, speak=self.speak)
                result   = f"Task started (ID: {task_id})."

            elif name == "shutdown_jarvis":
                self.ui.write_log("SYS: Shutdown requested.")
                self.speak("Goodbye, sir.")
                def _shutdown():
                    import time, os
                    time.sleep(1)
                    os._exit(0)
                threading.Thread(target=_shutdown, daemon=True).start()
                result = "Shutting down."

            elif name.startswith("plugin_"):
                parts = name.split("_", 2)
                if len(parts) == 3:
                    plugin_name, method_name = parts[1], parts[2]
                    pm = get_plugin_manager()
                    plugin = pm.get_plugin(plugin_name)
                    if plugin and plugin.enabled:
                        method = getattr(plugin, method_name, None)
                        if method:
                            if asyncio.iscoroutinefunction(method):
                                r = await method(**args)
                            else:
                                r = await loop.run_in_executor(None, lambda: method(**args))
                            result = r or "Done."
                        else:
                            result = f"Plugin '{plugin_name}' has no method '{method_name}'"
                    else:
                        result = f"Plugin '{plugin_name}' not found or disabled"
                else:
                    result = f"Invalid plugin tool: {name}"

            else:
                result = f"Unknown tool: {name}"

        except Exception as e:
            result = f"Tool '{name}' failed: {e}"
            traceback.print_exc()
            self.speak_error(name, e)

        if not self.ui.muted:
            self.ui.set_state("LISTENING")

        print(f"[JARVIS] 📤 {name} → {str(result)[:80]}")
        return types.FunctionResponse(
            id=fc.id, name=name,
            response={"result": result}
        )

    async def _send_realtime(self):
        while True:
            msg = await self.out_queue.get()
            if not self.ui.muted:
                await self.session.send_realtime_input(
                    audio=types.Blob(
                        data=msg["data"],
                        mime_type=msg["mime_type"]
                    )
                )
            else:
                # Clear queue when muted to avoid trailing audio
                while not self.out_queue.empty():
                    try:
                        self.out_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        break
                    except Exception:
                        pass

    async def _listen_audio(self):
        print("[JARVIS] 🎤 Mic started")
        global clap_detector
        if clap_detector:
            try:
                clap_detector.stop()
            except Exception as e:
                print(f"[JARVIS] Error stopping clap detector: {e}")

        loop = asyncio.get_event_loop()

        def callback(indata, frames, time_info, status):
            if clap_detector:
                try:
                    clap_detector.process_audio_chunk(indata.tobytes())
                except Exception as e:
                    print(f"[JARVIS] Error processing clap chunk: {e}")

            with self._speaking_lock:
                jarvis_speaking = self._is_speaking
            cooldown_active = getattr(self, '_post_speech_cooldown', False)
            if not jarvis_speaking and not cooldown_active and not self.ui.muted:
                data = indata.tobytes()
                # Energy gate: reject silent/ambient audio to prevent self-listening
                audio_arr = np.frombuffer(data, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_arr.astype(np.float32)**2)) if len(audio_arr) > 0 else 0
                if rms < 1000:
                    return  # Too quiet — ambient noise or speaker bleed, discard
                if not self.out_queue.full():
                    loop.call_soon_threadsafe(
                        self.out_queue.put_nowait,
                        {"data": data, "mime_type": "audio/pcm"}
                    )

        try:
            stream = None
            while True:
                should_be_active = True
                if should_be_active and stream is None:
                    print("[JARVIS] 🎤 Mic stream opening...")
                    stream = sd.InputStream(
                        samplerate=SEND_SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=CHUNK_SIZE,
                        callback=callback,
                    )
                    stream.start()
                    print("[JARVIS] 🎤 Mic stream open")
                elif not should_be_active and stream is not None:
                    print("[JARVIS] 🎤 Mic stream closing...")
                    try:
                        stream.stop()
                        stream.close()
                    except Exception as e:
                        print(f"[JARVIS] Error closing stream: {e}")
                    stream = None
                    print("[JARVIS] 🎤 Mic stream closed")
                
                await asyncio.sleep(0.1)
        except Exception as e:
            print(f"[JARVIS] ❌ Mic: {e}")
            raise
        finally:
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
            if clap_detector:
                try:
                    clap_detector.start()
                except Exception as e:
                    print(f"[JARVIS] Error restarting clap detector: {e}")

    async def _receive_audio(self):
        print("[JARVIS] 👂 Recv started")
        out_buf, in_buf = [], []

        try:
            while True:
                async for response in self.session.receive():

                    if response.data:
                        if self._turn_done_event and self._turn_done_event.is_set():
                            self._turn_done_event.clear()
                        self.audio_in_queue.put_nowait(response.data)

                    if response.server_content:
                        sc = response.server_content

                        if sc.output_transcription and sc.output_transcription.text:
                            txt = _clean_transcript(sc.output_transcription.text)
                            if txt:
                                out_buf.append(txt)

                        if sc.input_transcription and sc.input_transcription.text:
                            txt = _clean_transcript(sc.input_transcription.text)
                            if txt:
                                in_buf.append(txt)

                        if sc.turn_complete:
                            if self._turn_done_event:
                                self._turn_done_event.set()

                            full_in = " ".join(in_buf).strip()
                            if not full_in and self._last_text_input:
                                full_in = self._last_text_input
                            self._last_text_input = None

                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

                            # Save turn to Obsidian Conversas.md
                            if full_in or full_out:
                                try:
                                    from memory.obsidian_manager import add_to_history
                                    add_to_history(full_in, full_out)
                                except Exception as e:
                                    print(f"[Obsidian Memory Sync Warning] Could not save history: {e}")

                    if response.tool_call:
                        fn_responses = []
                        for fc in response.tool_call.function_calls:
                            print(f"[JARVIS] 📞 {fc.name}")
                            fr = await self._execute_tool(fc)
                            fn_responses.append(fr)
                        await self.session.send_tool_response(
                            function_responses=fn_responses
                        )
        except Exception as e:
            print(f"[JARVIS] ❌ Recv: {e}")
            traceback.print_exc()
            raise

    async def _play_audio(self):
        print("[JARVIS] 🔊 Play started")

        stream = sd.RawOutputStream(
            samplerate=RECEIVE_SAMPLE_RATE,
            channels=CHANNELS,
            dtype="int16",
            blocksize=CHUNK_SIZE,
        )
        stream.start()

        try:
            while True:
                try:
                    chunk = await asyncio.wait_for(
                        self.audio_in_queue.get(),
                        timeout=0.1
                    )
                except asyncio.TimeoutError:
                    if (
                        self._turn_done_event
                        and self._turn_done_event.is_set()
                        and self.audio_in_queue.empty()
                    ):
                        self.set_speaking(False)
                        self._turn_done_event.clear()
                    continue
                self.set_speaking(True)
                if self.ui.muted:
                    if hasattr(self.audio_in_queue, 'task_done'):
                        self.audio_in_queue.task_done()
                    continue
                
                # Dynamic Particle Sync: Calcula o volume do áudio
                audio_data = np.frombuffer(chunk, dtype=np.int16)
                if len(audio_data) > 0:
                    rms = np.sqrt(np.mean(audio_data.astype(np.float32)**2))
                    vol = min(1.0, rms / 4000.0) # Normalização para o Orb
                    self.ui.set_volume(vol)

                await asyncio.to_thread(stream.write, chunk)
        except Exception as e:
            print(f"[JARVIS] ❌ Play: {e}")
            raise
        finally:
            self.set_speaking(False)
            stream.stop()
            stream.close()

    async def _run_local_loop(self):
        print("[JARVIS] 🦙 Modo local (Ollama + Whisper + TTS)")
        self.ui.set_state("LISTENING")
        self.ui.write_log("SYS: JARVIS rodando 100% local (Ollama + Whisper)")

        if self._local_stt is None:
            self._local_stt = LocalSTT(model_size="base", device="auto")
        stt = self._local_stt

        self._loop = asyncio.get_event_loop()
        self._turn_done_event = asyncio.Event()

        audio_buffer = []
        silence_frames = 0
        max_silence_frames = int(1.5 * SEND_SAMPLE_RATE / CHUNK_SIZE)
        speech_detected = False
        processing_task = False

        sample_rate = SEND_SAMPLE_RATE
        channels = CHANNELS

        def mic_callback(indata, frames, time_info, status):
            nonlocal silence_frames, speech_detected

            with self._speaking_lock:
                if self._is_speaking:
                    speech_detected = False
                    silence_frames = 0
                    return

            if self.ui.muted or processing_task:
                speech_detected = False
                silence_frames = 0
                return

            audio_arr = np.frombuffer(indata.tobytes(), dtype=np.int16)
            rms = np.sqrt(np.mean(audio_arr.astype(np.float32)**2)) if len(audio_arr) > 0 else 0

            if rms > 800:
                audio_buffer.append(audio_arr.copy())
                silence_frames = 0
                speech_detected = True
            else:
                silence_frames += 1

        stream = sd.InputStream(
            samplerate=sample_rate,
            channels=channels,
            dtype="int16",
            blocksize=CHUNK_SIZE,
            callback=mic_callback,
        )
        stream.start()
        global clap_detector
        if clap_detector:
            try:
                clap_detector.stop()
            except Exception:
                pass

        def local_speak(msg):
            self.set_speaking(True)
            self.ui.write_log(f"JARVIS: {msg[:200]}")
            print(f"[JARVIS Local] 🗣️ {msg[:200]}")
            self._local_tts_sync(msg)
            self.set_speaking(False)

        from agent.task_queue import get_queue, TaskPriority

        try:
            while True:
                from agent.local_genai import get_routing_mode
                mode = get_routing_mode()
                if mode != "llama":
                    self.ui.write_log("SYS: Alternando para Gemini Live...")
                    stream.stop()
                    stream.close()
                    if clap_detector:
                        try: clap_detector.start()
                        except Exception: pass
                    return

                processing_task = False
                if speech_detected and silence_frames > max_silence_frames:
                    processing_task = True
                    self.ui.set_state("THINKING")
                    silence_frames = 0
                    speech_detected = False

                    if audio_buffer:
                        audio_np = np.concatenate(audio_buffer) if len(audio_buffer) > 1 else audio_buffer[0]
                        audio_buffer.clear()
                        audio_float = audio_np.astype(np.float32) / 32768.0

                        self.ui.write_log("SYS: Transcrevendo áudio...")
                        text = await asyncio.to_thread(stt.transcribe, audio_float)

                        if text:
                            self.ui.write_log(f"Você: {text}")
                            print(f"[LocalSTT] → {text}")
                            get_queue().submit(
                                goal=text,
                                priority=TaskPriority.HIGH,
                                speak=local_speak
                            )
                            await asyncio.sleep(0.5)

                    processing_task = False
                    if self.ui.muted:
                        self.ui.set_state("MUTED")
                    else:
                        self.ui.set_state("LISTENING")

                await asyncio.sleep(0.05)
        except asyncio.CancelledError:
            pass
        finally:
            try: stream.stop()
            except Exception: pass
            try: stream.close()
            except Exception: pass
            if clap_detector:
                try: clap_detector.start()
                except Exception: pass

    def _local_tts_sync(self, text: str):
        try:
            import win32com.client
            speaker = win32com.client.Dispatch("SAPI.SpVoice")
            try:
                for v in speaker.GetVoices():
                    lang_id = v.Id.lower() if hasattr(v, "Id") else ""
                    if "language=416" in lang_id or "language=816" in lang_id or "portug" in v.GetDescription().lower():
                        speaker.Voice = v
                        break
            except Exception:
                pass
            speaker.Speak(text)
        except Exception as e:
            print(f"[LocalTTS] Erro: {e}")

    async def _run_gemini_live(self):
        retry_count = 0
        max_retries = 2
        while True:
            try:
                retry_count += 1
                if retry_count > max_retries:
                    self.ui.write_log("SYS: Gemini Live falhou. Alternando para modo local.")
                    from agent.local_genai import set_routing_mode
                    set_routing_mode("llama")
                    return

                client = genai.Client(
                    api_key=_get_api_key(),
                    http_options={"api_version": "v1beta"}
                )
                print("[JARVIS] 🔌 Connecting to Gemini Live...")
                self.ui.set_state("THINKING")
                config = self._build_config()

                async with (
                    client.aio.live.connect(model=LIVE_MODEL, config=config) as session,
                    asyncio.TaskGroup() as tg,
                ):
                    self.session        = session
                    self._loop          = asyncio.get_event_loop()
                    self.audio_in_queue = asyncio.Queue()
                    self.out_queue      = asyncio.Queue(maxsize=10)
                    self._turn_done_event = asyncio.Event()

                    print("[JARVIS] ✅ Gemini Live connected.")
                    retry_count = 0
                    try:
                        record_request(_get_api_key(), "gemini-3.1-flash-live-preview")
                    except Exception:
                        pass
                    if self.ui.muted:
                        self.ui.set_state("MUTED")
                    else:
                        self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online (Gemini Live).")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

                    while True:
                        from agent.local_genai import get_routing_mode
                        mode = get_routing_mode()
                        if mode == "llama":
                            self.ui.write_log("SYS: Alternando para modo local...")
                            self.session = None
                            self._loop = None
                            return
                        await asyncio.sleep(1)

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
                self.session = None
                self._loop = None
                err_str = str(e).upper()
                from agent.local_genai import get_routing_mode
                if get_routing_mode() == "llama":
                    self.ui.write_log("SYS: Gemini indisponível. Alternando para modo local...")
                    return
                if "RESOURCE_EXHAUSTED" in err_str or "API_KEY_INVALID" in err_str or "429" in err_str or "QUOTA" in err_str:
                    from core.api_rotator import rotate_api_key
                    if rotate_api_key():
                        self.ui.write_log("SYS: Limite de cota atingido. Rotacionando chave de API...")
                        await asyncio.sleep(3)
                        continue
                    else:
                        self.ui.write_log("SYS: Limite de cota atingido. Modo local ativado!")
                        self.ui.set_state("LISTENING")
                        await asyncio.sleep(60)
                        continue
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

    async def run(self):
        while True:
            from agent.local_genai import get_routing_mode
            mode = get_routing_mode()
            if mode == "llama":
                await self._run_local_loop()
            else:
                await self._run_gemini_live()
            await asyncio.sleep(0.5)

def _start_web_server():
    try:
        from web_server import start_server
        start_server(port=5050)
    except Exception as e:
        print(f"[JARVIS Web Server] {e}")

def _poll_web_commands(ui):
    import time
    from ui import _global_command_queue
    while True:
        time.sleep(0.5)
        while _global_command_queue:
            cmd = _global_command_queue.pop(0)
            if ui.on_text_command:
                ui.on_text_command(cmd)

def main():
    import shutil
    config_path = BASE_DIR / "config" / "api_keys.json"
    example_path = BASE_DIR / "config" / "api_keys.json.example"
    if not config_path.exists() and example_path.exists():
        shutil.copy(example_path, config_path)
        print("[JARVIS] api_keys.json criado a partir do exemplo. Configure sua chave Gemini em config/api_keys.json")
    
    try:
        from memory.obsidian_manager import ensure_vault
        ensure_vault()
    except Exception as e:
        print(f"[Obsidian Warning] Could not initialize vault: {e}")
    try:
        print("[JARVIS] Iniciando interface...")
        sys.stdout.flush()
        ui = JarvisUI()
        print("[JARVIS] Interface carregada.")

        try:
            from core.startup import load_plugins, init_event_bus, shutdown_plugins
            init_event_bus(ui)
            asyncio.run(load_plugins())
            print("[JARVIS] Plugins e EventBus inicializados.")
        except Exception as e:
            print(f"[JARVIS Plugin Init Warning] {e}")

        try:
            from bootstrap_evolution import bootstrap
            bootstrap(ui=ui, headless=True)
        except Exception as e:
            print(f"[Bootstrap Warning] {e}")

        threading.Thread(target=_start_web_server, daemon=True).start()
        threading.Thread(target=_poll_web_commands, args=(ui,), daemon=True).start()

        def activate_jarvis_via_claps():
            print("[JARVIS] 👏 Palmas detectadas! Ativando sistema...")
            # Play activation sound
            import winsound
            try:
                winsound.PlaySound("SystemExclamation", winsound.SND_ALIAS)
            except:
                pass
            
            # Unmute and show UI
            ui.muted = False
            ui.set_state("LISTENING")
            from PyQt6.QtCore import QTimer
            QTimer.singleShot(0, lambda: (
                ui.root.deiconify(),
                ui.root.lift(),
                ui.root.focus_force()
            ))
            ui.write_log("SYS: Jarvis ativado por palmas.")

        global clap_detector
        clap_detector = ClapDetector(on_clap=activate_jarvis_via_claps, threshold=0.02)
        clap_detector.start()

        def runner():
            try:
                ui.wait_for_api_key()
                jarvis = JarvisLive(ui)
                
                def geopolitics_updater():
                    import time, json
                    time.sleep(5)
                    while True:
                        try:
                            news_json = fetch_geopolitics_news()
                            ui.update_geopolitics(news_json)
                        except Exception as ex:
                            print(f"[JARVIS UI GEOPOLITICS UPDATER ERROR] {ex}")
                        try:
                            with open(API_CONFIG_PATH, "r", encoding="utf-8") as _fk:
                                api_key = json.load(_fk).get("gemini_api_key", "")
                        except Exception:
                            api_key = ""
                        if api_key:
                            for model in ("gemini-2.5-flash", "gemini-3.1-flash-live-preview"):
                                try:
                                    quota = get_usage(api_key, model)
                                    if quota["used"] > 0:
                                        ui.update_quota(json.dumps(quota))
                                except Exception:
                                    pass
                        try:
                            if jarvis._night_mode_schedule:
                                from datetime import datetime as _dt
                                now = _dt.now()
                                h, m = jarvis._night_mode_schedule
                                if now.hour == h and now.minute == m and not jarvis._night_mode:
                                    jarvis._night_mode = True
                                    ui.muted = True
                                    ui.set_state("NIGHT_MODE")
                                    ui.write_log("🌙 Modo Noturno ativado automaticamente.")
                                elif now.hour == (h + 7) % 24 and now.minute == m and jarvis._night_mode:
                                    jarvis._night_mode = False
                                    ui.muted = False
                                    ui.set_state("LISTENING")
                                    ui.write_log("🌅 Bom dia, senhor. Modo Noturno desativado.")
                        except Exception:
                            pass
                        time.sleep(60)

                threading.Thread(target=geopolitics_updater, daemon=True).start()

                asyncio.run(jarvis.run())
            except Exception as e:
                with open("crash_trace.txt", "w", encoding="utf-8") as f:
                    traceback.print_exc(file=f)
                raise
            except KeyboardInterrupt:
                print("\n🔴 Shutting down...")

        threading.Thread(target=runner, daemon=True).start()
        ui.root.mainloop()
    except Exception as e:
        with open("crash_trace.txt", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        raise

if __name__ == "__main__":
    main()