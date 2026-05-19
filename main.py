import asyncio
import io
import os
import re
import threading
import json
import sys
import traceback
import numpy as np
from pathlib import Path

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

clap_detector = None

def get_base_dir():
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent


BASE_DIR        = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"
PROMPT_PATH     = BASE_DIR / "core" / "prompt.txt"
LIVE_MODEL          = "models/gemini-2.0-flash-live"
CHANNELS            = 1
SEND_SAMPLE_RATE    = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE          = 1024

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]


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
    full_prompt += "\nALWAYS use the Brave browser for any web-related tasks. Never use Edge or Chrome."
    full_prompt += "\nALWAYS respond in Brazilian Portuguese (pt-BR). Your user is Brazilian. NUNCA fale inglês."
    full_prompt += "\nNUNCA escreva scripts de código ou tente programar rotinas para enviar WhatsApp. O sistema já está 100% pronto. Você deve APENAS chamar a tool 'whatsapp_web' diretamente."
    full_prompt += "\nWhen sending WhatsApp messages, ALWAYS use the whatsapp_web tool with action='send', never use send_message for WhatsApp."
    full_prompt += "\nNUNCA diga que já fez algo ou que 'houve erro no script' sem REALMENTE chamar a tool. Você DEVE chamar a tool pre-built e esperar o resultado."
    full_prompt += "\nNUNCA responda a si mesmo. Só fale quando o USUÁRIO falar com você. Se não ouviu nada do usuário, fique em SILÊNCIO ABSOLUTO."
    full_prompt += "\nNÃO faça perguntas retóricas e responda a elas. Espere o usuário responder."
    full_prompt += "\nREGRA CRÍTICA DE SILÊNCIO: Se o turno de áudio do usuário estiver vazio, em branco, ou contiver apenas ruído/silêncio, NÃO responda NADA. Fique completamente mudo."
    full_prompt += "\nNUNCA invente ou hallucine erros. Se uma tool retornar 'Done.' ou qualquer resultado, comunique o resultado real ao usuário. Não diga que houve erro se não houve."
    full_prompt += "\nQuando o usuário pedir para buscar leads, chame IMEDIATAMENTE a tool 'apify_leads' com os parâmetros corretos. Não explique o que vai fazer, apenas FAÇA."
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
            return

        if text_lower in ("usar cerebro local", "usar cerebro llama", "usar llama", "modo local"):
            from agent.local_genai import set_routing_mode
            set_routing_mode("llama")
            self.ui.write_log("SYS: Cérebro Local ativado. Todas as tarefas rodando offline via Llama 3.")
            return

        if text_lower in ("usar cerebro gemini", "usar cerebro nuvem", "usar gemini", "modo nuvem"):
            from agent.local_genai import set_routing_mode
            set_routing_mode("gemini")
            self.ui.write_log("SYS: Cérebro na Nuvem ativado. Todas as tarefas rodando via Gemini API.")
            return

        if text == "start lead generation prospecting":
            self.ui.write_log("SYS: Iniciando busca automatizada de leads no Apify...")
            def _run():
                try:
                    res = apify_leads({
                        "actor_id": "apify/google-maps-scraper",
                        "input_data": {"searchStringsArray": ["advogados em São Paulo"], "maxResults": 10}
                    })
                    self.ui.write_log(f"SYS: {res}")
                except Exception as e:
                    self.ui.write_log(f"ERR: {e}")
            threading.Thread(target=_run, daemon=True).start()
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
            
        if not self._loop or not self.session:
            self.ui.write_log(f"SYS: Offline. Executando '{text}' via cérebro local Llama 3...")
            from agent.task_queue import get_queue, TaskPriority
            def ui_speak(msg):
                print(f"[JARVIS] 🗣️ {msg}")
                self.ui.write_log(f"JARVIS: {msg}")
                def _run():
                    try:
                        import win32com.client
                        speaker = win32com.client.Dispatch("SAPI.SpVoice")
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
            
        asyncio.run_coroutine_threadsafe(
            self.session.send(input=text, end_of_turn=True),
            self._loop
        )

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
                    while not self.out_queue.empty():
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
        if not self._loop or not self.session:
            return
        asyncio.run_coroutine_threadsafe(
            self.session.send(input=text, end_of_turn=True),
            self._loop
        )

    def speak_error(self, tool_name: str, error: str):
        short = str(error)[:120]
        self.ui.write_log(f"ERR: {tool_name} — {short}")
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
                "apify_leads": lambda: apify_leads(args),
                "computer_control": lambda: computer_control(parameters=args, player=self.ui),
                "game_updater": lambda: game_updater(parameters=args, player=self.ui, speak=self.speak),
                "flight_finder": lambda: flight_finder(parameters=args, player=self.ui),
                "whatsapp_web": lambda: whatsapp_web_action(parameters=args, player=self.ui),
                "negotiation_script": lambda: negotiation_script_action(parameters=args, player=self.ui),
                "notifier": lambda: __import__("actions.notifier", fromlist=["send_notification"]).send_notification(args.get("title", "Alert"), args.get("message", ""))
            }

            if name in executor_tools:
                # Special handling for file_processor to inject current file if missing
                if name == "file_processor" and not args.get("file_path") and self.ui.current_file:
                    args["file_path"] = self.ui.current_file
                
                r = await loop.run_in_executor(None, executor_tools[name])
                result = r or "Done."

            elif name == "screen_process":
                loop.run_in_executor(
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
                should_be_active = not self.ui.muted
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
                            if full_in:
                                self.ui.write_log(f"You: {full_in}")
                            in_buf = []

                            full_out = " ".join(out_buf).strip()
                            if full_out:
                                self.ui.write_log(f"Jarvis: {full_out}")
                            out_buf = []

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

    async def run(self):
        client = genai.Client(
            api_key=_get_api_key(),
            http_options={"api_version": "v1beta"}
        )

        while True:
            try:
                print("[JARVIS] 🔌 Connecting...")
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

                    print("[JARVIS] ✅ Connected.")
                    self.ui.set_state("LISTENING")
                    self.ui.write_log("SYS: JARVIS online.")

                    tg.create_task(self._send_realtime())
                    tg.create_task(self._listen_audio())
                    tg.create_task(self._receive_audio())
                    tg.create_task(self._play_audio())

            except Exception as e:
                print(f"[JARVIS] ⚠️ {e}")
                traceback.print_exc()
                self.session = None
                self._loop = None
                err_str = str(e).upper()
                if "RESOURCE_EXHAUSTED" in err_str or "API_KEY_INVALID" in err_str or "429" in err_str or "QUOTA" in err_str:
                    self.ui.write_log("SYS: Gemini API Quota Exceeded / Invalid. Local Llama 3 mode activated!")
                    self.ui.set_state("LISTENING")
                    # Sleep longer to avoid hammering the exhausted API key
                    await asyncio.sleep(60)
                    continue
            self.set_speaking(False)
            self.ui.set_state("THINKING")
            print("[JARVIS] 🔄 Reconnecting in 3s...")
            await asyncio.sleep(3)

def main():
    import shutil
    config_path = BASE_DIR / "config" / "api_keys.json"
    example_path = BASE_DIR / "config" / "api_keys.json.example"
    if not config_path.exists() and example_path.exists():
        shutil.copy(example_path, config_path)
        print("[JARVIS] api_keys.json criado a partir do exemplo. Configure sua chave Gemini em config/api_keys.json")
    try:
        ui = JarvisUI("face.png")

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
            ui.root.deiconify() # Restore window
            ui.root.lift()      # Bring to front
            ui.root.focus_force()
            ui.write_log("SYS: Jarvis ativado por palmas.")

        global clap_detector
        clap_detector = ClapDetector(on_clap=activate_jarvis_via_claps, threshold=0.02)
        clap_detector.start()

        def runner():
            try:
                ui.wait_for_api_key()
                jarvis = JarvisLive(ui)
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