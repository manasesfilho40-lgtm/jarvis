import os
import platform
import re
import asyncio
import json
import time
import random
from pathlib import Path
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

def get_base_dir():
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

_KNOWN_COUNTRY_CODES = {
    "1",   # US/CA
    "7",   # RU/KZ
    "20",  # EG
    "27",  # ZA
    "30",  # GR
    "31",  # NL
    "32",  # BE
    "33",  # FR
    "34",  # ES
    "36",  # HU
    "39",  # IT
    "40",  # RO
    "41",  # CH
    "43",  # AT
    "44",  # UK
    "45",  # DK
    "46",  # SE
    "47",  # NO
    "48",  # PL
    "49",  # DE
    "51",  # PE
    "52",  # MX
    "53",  # CU
    "54",  # AR
    "55",  # BR
    "56",  # CL
    "57",  # CO
    "58",  # VE
    "60",  # MY
    "61",  # AU
    "62",  # ID
    "63",  # PH
    "64",  # NZ
    "65",  # SG
    "66",  # TH
    "81",  # JP
    "82",  # KR
    "84",  # VN
    "86",  # CN
    "90",  # TR
    "91",  # IN
    "92",  # PK
    "93",  # AF
    "94",  # LK
    "95",  # MM
    "98",  # IR
    "212", # MA
    "213", # DZ
    "216", # TN
    "218", # LY
    "220", # GM
    "234", # NG
    "254", # KE
    "255", # TZ
    "256", # UG
    "351", # PT
    "353", # IE
    "354", # IS
    "355", # AL
    "358", # FI
    "370", # LT
    "372", # EE
    "380", # UA
    "420", # CZ
    "421", # SK
    "502", # GT
    "503", # SV
    "504", # HN
    "505", # NI
    "506", # CR
    "507", # PA
    "591", # BO
    "593", # EC
    "595", # PY
    "598", # UY
    "961", # LB
    "962", # JO
    "963", # SY
    "964", # IQ
    "965", # KW
    "966", # SA
    "971", # AE
    "972", # IL
    "973", # BH
    "974", # QA
    "975", # BT
    "976", # MN
    "977", # NP
    "992", # TJ
    "993", # TM
    "994", # AZ
    "995", # GE
    "996", # KG
    "998", # UZ
}

def _get_api_key() -> str:
    try:
        with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            key = data.get("gemini_api_key", "")
            if not key:
                keys = data.get("gemini_api_keys", [])
                key = keys[0] if keys else ""
            return key
    except (FileNotFoundError, json.JSONDecodeError, IndexError, KeyError):
        return ""

def _normalize_phone(phone_str: str) -> str:
    if not phone_str:
        return ""
    digits = "".join(c for c in phone_str if c.isdigit())
    if not digits:
        return ""

    if digits.startswith("55") and len(digits) >= 12:
        return digits

    had_plus = phone_str.strip().startswith("+")
    if had_plus:
        for code_len in (3, 2, 1):
            if len(digits) > code_len and digits[:code_len] in _KNOWN_COUNTRY_CODES:
                return digits

    br_ddd = digits[:2]
    if len(digits) in (10, 11) and br_ddd.isdigit() and 11 <= int(br_ddd) <= 99:
        return "55" + digits

    if len(digits) <= 11:
        return "55" + digits

    return digits

class WhatsAppWeb:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None
        self._stop = False
        self._stop_event = asyncio.Event()
        self._conversation_history = []

    async def check_and_dismiss_popups(self):
        try:
            blocker_texts = ["Usar nesta janela", "Usar aqui", "Use here"]
            for text in blocker_texts:
                locs = self.page.locator(f"button:has-text('{text}'), div[role='button']:has-text('{text}')")
                count = await locs.count()
                for i in range(count):
                    el = locs.nth(i)
                    try:
                        if await el.is_visible():
                            await el.click(force=True)
                            await asyncio.sleep(2)
                            return True
                    except Exception:
                        pass

            dialogs = self.page.locator("div[role='dialog'], div[role='alertdialog']")
            dialog_count = await dialogs.count()
            for i in range(dialog_count):
                dialog = dialogs.nth(i)
                try:
                    if await dialog.is_visible():
                        text_content = await dialog.inner_text()
                        low_text = text_content.lower()
                        if any(term in low_text for term in ["não está no whatsapp", "não está", "is not on whatsapp", "inválido", "invalid"]):
                            ok_btn = dialog.get_by_text(re.compile("^OK$", re.IGNORECASE))
                            if await ok_btn.count() > 0:
                                await ok_btn.first.click(force=True)
                                await asyncio.sleep(1)
                            raise ValueError(f"PHONE_INVALID: {text_content.strip()}")
                except ValueError:
                    raise
                except Exception:
                    pass
        except ValueError:
            raise
        except Exception as e:
            print(f"[WhatsApp] Popup check error: {e}")
        return False

    async def start(self):
        self.playwright = await async_playwright().start()

        _sn = platform.system()
        if _sn == "Windows":
            localappdata = os.environ.get("LOCALAPPDATA", os.path.expanduser("~\\AppData\\Local"))
            progfiles = os.environ.get("PROGRAMFILES", "C:\\Program Files")
            user_data_dir = os.path.join(localappdata, "BraveSoftware", "Brave-Browser", "JarvisProfile")
            brave_path = os.path.join(progfiles, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
            if not os.path.exists(brave_path):
                brave_path = os.path.join(localappdata, "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
        elif _sn == "Darwin":
            user_data_dir = os.path.join(os.path.expanduser("~"), "Library", "Application Support", "BraveSoftware", "Brave-Browser", "JarvisProfile")
            brave_path = "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser"
        else:
            user_data_dir = os.path.join(os.path.expanduser("~"), ".config", "brave", "JarvisProfile")
            brave_path = "brave"

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir,
                executable_path=brave_path if os.path.exists(brave_path) else None,
                headless=False,
                args=["--remote-debugging-port=9222"]
            )
        except Exception as launch_err:
            print(f"[WhatsApp] Persistent launch failed: {launch_err}. Trying fallback...")
            import tempfile
            temp_profile = os.path.join(tempfile.gettempdir(), f"jarvis_temp_profile_{random.randint(1000, 9999)}")
            self.context = await self.playwright.chromium.launch_persistent_context(
                temp_profile,
                executable_path=brave_path if os.path.exists(brave_path) else None,
                headless=False,
                args=[]
            )

        try:
            if self.context.pages:
                self.page = self.context.pages[-1]
                for p in self.context.pages[:-1]:
                    await p.close()
            else:
                self.page = await self.context.new_page()

            await self.page.goto("https://web.whatsapp.com", timeout=60000)
            print("[WhatsApp] Browser started and navigated to WhatsApp Web.")

            for _ in range(15):
                await self.check_and_dismiss_popups()
                await asyncio.sleep(1)
        except Exception as e:
            print(f"[WhatsApp] Error starting browser/page: {e}")
            await self.stop()
            raise

    async def stop(self):
        self._stop = True
        self._stop_event.set()
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
        if self.playwright:
            try:
                await self.playwright.stop()
            except Exception:
                pass

    async def _is_browser_alive(self) -> bool:
        if not self.page:
            return False
        try:
            await self.page.evaluate("() => document.title")
            return True
        except Exception:
            return False

    async def open_chat(self, name_or_number):
        resolved_phone = ""
        try:
            from actions.leads_manager import init_db
            db = init_db()
            name_clean = str(name_or_number).lower().strip()
            for lead in db.get("new", []) + db.get("used", []):
                title = str(lead.get("title", "")).lower().strip()
                if name_clean in title or title in name_clean:
                    phone = lead.get("phoneUnformatted")
                    if phone:
                        resolved_phone = phone
                        print(f"[WhatsApp] Resolved '{name_or_number}' to '{phone}' from CRM.")
                        break
        except Exception as e:
            print(f"[WhatsApp CRM Resolve Warning] {e}")

        target_to_check = resolved_phone if resolved_phone else name_or_number
        clean_num = _normalize_phone(target_to_check)
        is_phone = clean_num.isdigit() and len(clean_num) >= 8

        if is_phone:
            print(f"[WhatsApp] Opening direct chat for: {clean_num}")
            await self.page.goto(f"https://web.whatsapp.com/send?phone={clean_num}")
            for _ in range(15):
                await self.check_and_dismiss_popups()
                await asyncio.sleep(1)
            return

        search_box = self.page.locator("div[contenteditable='true'][data-tab='3'], [placeholder='Pesquisar ou começar uma nova conversa']")

        for _ in range(120):
            await self.check_and_dismiss_popups()
            try:
                if await search_box.is_visible():
                    break
            except Exception:
                pass
            await asyncio.sleep(1)

        await search_box.click()
        await search_box.fill("")
        await search_box.type(name_or_number)
        await asyncio.sleep(2)

        chat_selector = f"span[title='{name_or_number}']"
        try:
            await self.page.click(chat_selector, timeout=5000)
        except Exception:
            await self.page.keyboard.press("Enter")

        await asyncio.sleep(1)

    async def send_message(self, message):
        input_box = await self.page.wait_for_selector(
            "footer div[contenteditable='true'], div[data-tab='10']",
            timeout=15000
        )
        if not input_box:
            raise Exception("Campo de mensagem não encontrado.")
        await input_box.click()

        char_delay = max(0.01, min(0.05, 0.05 - (len(message) * 0.0003)))
        for char in message:
            await self.page.keyboard.type(char)
            await asyncio.sleep(random.uniform(char_delay * 0.7, char_delay * 1.3))

        await asyncio.sleep(random.uniform(0.4, 0.9))
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(0.5)

        try:
            send_btn = await self.page.query_selector("span[data-icon='send']")
            if send_btn:
                await send_btn.click()
        except Exception:
            pass

    async def get_last_messages(self, limit=5):
        results = []
        try:
            message_bubbles = await self.page.query_selector_all(
                "div[data-testid='bubble-body'] span.selectable-text, "
                "div[data-testid='bubble-body'] span[dir='auto']"
            )
            for msg in message_bubbles[-limit:]:
                try:
                    text = await msg.inner_text()
                    if text and text.strip():
                        results.append(text.strip())
                except Exception:
                    continue

            if not results:
                containers = await self.page.query_selector_all(".message-in, .message-out")
                for msg in containers[-limit:]:
                    try:
                        text = await msg.inner_text()
                        if text:
                            lines = text.strip().split("\n")
                            if len(lines) > 1 and ("AM" in lines[-1] or "PM" in lines[-1] or ":" in lines[-1]):
                                text = "\n".join(lines[:-1])
                            if text.strip():
                                results.append(text.strip())
                    except Exception:
                        continue
        except Exception as e:
            print(f"[WhatsApp] get_last_messages error: {e}")

        return results

    async def _get_or_create_script(self, product_name, player=None):
        from actions.negotiation_script import load_script
        script = load_script(product_name)
        if not script:
            if player:
                player.write_log(f"SYS: Roteiro não encontrado para '{product_name}'. Gerando automaticamente...")
            try:
                from actions.negotiation_script import generate_negotiation_script
                generate_negotiation_script(
                    product=product_name,
                    price="R$ 10/foto (pacote 15 fotos por R$ 120)",
                    max_discount="20%",
                    tone="casual"
                )
                script = load_script(product_name)
            except Exception as e:
                print(f"[WhatsApp] Script generation error: {e}")

            if not script:
                script = {
                    "opening_message": f"Opa, tudo certo? Vi que sua loja vende online — já pensou em ter anúncios com fotos mais profissionais pros seus produtos? Trabalho com criação de criativos que aumentam conversão.",
                    "objection_handling": {
                        "nao_temos_interesse": "Tranquilo! Se mudar de ideia, meu contato tá aqui. Sucesso com a marca!",
                        "ja_temos_agencia": "Show! Atuo como braço de apoio pra agências também, atendendo demandas pontuais. Se um dia precisarem de reforço, é só chamar.",
                        "preco_alto": "Entendo! Que tal testarmos com uma única arte primeiro, sem compromisso? Se gostar do resultado, a gente monta um pacote depois.",
                        "sem_verba_agora": "Sem problema! Vou deixar meu contato aqui. Quando tiver verba, me chama que faço um preço especial pra lojas parceiras.",
                        "preciso_consultar": "Claro, sem pressa! Enquanto isso, posso te mandar alguns exemplos de anúncios que já criei pra lojas do mesmo segmento?",
                        "manda_email": "Mando sim! Mas se puder, me fala qual tipo de peça vc mais precisa (story, feed, catálogo) pra eu preparar algo direcionado.",
                        "nao_confio": "Super entendo! Quer dar uma olhada no meu portfólio? Já criei anúncios pra lojas como [X] e [Y] que aumentaram as vendas em [Z]%",
                        "ja_temos_fornecedor": "Que bom! Se um dia precisar de um segundo fornecedor ou de ajuda com picos de demanda, tô aqui."
                    },
                    "counter_proposal": "Que tal testar com 1 arte primeiro por R$ 50? Se gostar, fechamos um pacote depois.",
                    "closing_message": "Perfeito! Me envia o logo e as referências de estilo que já preparo a primeira arte em até 24h.",
                    "follow_up": "Opa, tudo bem? Passei aqui porque criei um modelo novo que pode se encaixar bem no seu tipo de produto. Quer dar uma olhada rápida?",
                    "urgency_triggers": {
                        "scarcity": "Essa semana ainda tenho 2 vagas pra projetos novos, depois só mês que vem.",
                        "social_proof": "Essa semana fechei com 3 lojas do ramo e todas tão vendo resultado em vendas já nos primeiros dias."
                    },
                    "metadata": {"product": product_name, "price": "R$ 10/foto (15 por R$ 120)", "max_discount": "20%"}
                }
        return script

    async def guard_loop(self, target, message=None, player=None, timeout_minutes=60, product_name=None):
        """Sends a message (if provided) then stays in the chat monitoring for replies.
        If product_name is provided, automatically responds to lead replies using the negotiation script."""
        self._conversation_history = []

        script = None
        if product_name:
            script = await self._get_or_create_script(product_name, player)

        if player:
            player.write_log(f"SYS: Modo guarda ativado para {target}. Monitorando por {timeout_minutes} minutos...")

        if message:
            try:
                await self.send_message(message)
                self._conversation_history.append({"role": "assistant", "content": message})
                if player:
                    player.write_log("SYS: Mensagem enviada. Aguardando resposta do lead...")
            except Exception as e:
                print(f"[WhatsApp] Guard send error: {e}")
                if player:
                    player.write_log(f"ERR: Falha ao enviar: {e}")

        last_seen_msg = None
        reply_count = 0
        start_time = time.time()
        timeout_seconds = timeout_minutes * 60

        while not self._stop:
            if not await self._is_browser_alive():
                if player:
                    player.write_log("ERR: Browser fechado. Encerrando guarda.")
                return

            elapsed = time.time() - start_time
            if elapsed > timeout_seconds:
                if player:
                    player.write_log(f"SYS: Timeout de {timeout_minutes}min atingido. Encerrando guarda.")
                return

            try:
                msgs = await self.get_last_messages(limit=3)
                if msgs:
                    newest = msgs[-1]
                    if newest != last_seen_msg:
                        last_container = None
                        containers = await self.page.query_selector_all(".message-in, .message-out")
                        if containers:
                            last_container = containers[-1]
                            classes = await last_container.evaluate("el => el.className")

                        if last_container and "message-in" in classes:
                            reply_count += 1
                            last_seen_msg = newest
                            self._conversation_history.append({"role": "user", "content": newest})

                            if player:
                                player.write_log(f"LEADS: {target} respondeu: '{newest[:50]}...'")

                            try:
                                from actions.notifier import notify_client_reply
                                notify_client_reply(f"{target} respondeu: {newest}")
                            except Exception:
                                pass

                            if script:
                                if player:
                                    player.write_log("JARVIS: Gerando resposta automática...")
                                reply = await self._generate_reply(newest, script)
                                await self.send_message(reply)
                                self._conversation_history.append({"role": "assistant", "content": reply})
                                if player:
                                    player.write_log(f"JARVIS: Resposta automática enviada.")
                            else:
                                if reply_count == 1:
                                    if player:
                                        player.write_log("JARVIS: Primeira resposta detectada! Mantendo monitoramento...")
                        else:
                            last_seen_msg = newest

                await asyncio.sleep(3)
            except Exception as e:
                print(f"[WhatsApp] Guard loop error: {e}")
                await asyncio.sleep(10)

    async def autonomous_loop(self, product_name, player=None, max_messages=20):
        script = await self._get_or_create_script(product_name, player)
        self._conversation_history = []

        if player:
            player.write_log(f"SYS: Iniciando fluxo de negociação para '{product_name}'...")

        opening = script.get("opening_message", "Bom dia, preciso falar com o responsável pelo marketing ou pelo comercial — é sobre uma proposta de divulgação pra empresa.")
        if player:
            player.write_log("SYS: Enviando mensagem padrão de contato inicial...")

        try:
            await self.send_message(opening)
            self._conversation_history.append({"role": "assistant", "content": opening})
            if player:
                player.write_log("SYS: Mensagem inicial enviada! Aguardando respostas do lead...")
        except Exception as e:
            print(f"[WhatsApp] Error sending opening message: {e}")
            if player:
                player.write_log(f"ERR: Falha ao enviar mensagem inicial: {e}")
            return

        last_seen_msg = None
        message_count = 0

        while not self._stop and message_count < max_messages:
            try:
                if not await self._is_browser_alive():
                    if player:
                        player.write_log("ERR: Browser fechado. Encerrando negociação.")
                    return

                containers = await self.page.query_selector_all(".message-in, .message-out")
                if containers:
                    last_container = containers[-1]
                    classes = await last_container.evaluate("el => el.className")
                    if "message-out" in classes:
                        text = await last_container.inner_text()
                        if text:
                            lines = text.strip().split("\n")
                            if len(lines) > 1 and ("AM" in lines[-1] or "PM" in lines[-1] or ":" in lines[-1]):
                                text = "\n".join(lines[:-1])
                            last_seen_msg = text.strip()
                        await asyncio.sleep(5)
                        continue

                msgs = await self.get_last_messages(limit=1)
                if msgs and msgs[-1] != last_seen_msg:
                    incoming = msgs[-1]
                    last_seen_msg = incoming
                    self._conversation_history.append({"role": "user", "content": incoming})
                    print(f"[WhatsApp] New message: {incoming}")
                    if player:
                        player.write_log("LEADS: Nova mensagem recebida...")

                    reply = await self._generate_reply(incoming, script)
                    print(f"[WhatsApp] Replying: {reply}")

                    if player:
                        player.write_log("JARVIS: Digitando resposta...")

                    await self.send_message(reply)
                    self._conversation_history.append({"role": "assistant", "content": reply})
                    message_count += 1

                    if player:
                        player.write_log(f"JARVIS: Resposta enviada ({message_count}/{max_messages}).")

                    try:
                        from actions.notifier import notify_client_reply
                        notify_client_reply(incoming)
                    except Exception:
                        pass

                await asyncio.sleep(5)
            except Exception as e:
                print(f"[WhatsApp] Loop error: {e}")
                await asyncio.sleep(10)

        if player:
            player.write_log(f"SYS: Negociação encerrada ({message_count} mensagens trocadas).")

    async def multi_autonomous_loop(self, product_name, player=None, max_leads_per_cycle=50):
        script = await self._get_or_create_script(product_name, player)
        self._conversation_history = []

        from actions.leads_manager import get_new_leads, mark_as_used, get_db_lock

        if player:
            player.write_log("SYS: Iniciando prospecção inteligente com base no banco de leads...")

        cycle_count = 0
        max_cycles = 100
        stats = {"enviadas": 0, "respondidas": 0, "invalidos": 0, "erros": 0, "pulos": 0}

        while not self._stop and cycle_count < max_cycles:
            if not await self._is_browser_alive():
                if player:
                    player.write_log("ERR: Browser fechado. Tentando reabrir...")
                try:
                    await self.start()
                    if player:
                        player.write_log("SYS: Browser reaberto com sucesso.")
                except Exception as e:
                    if player:
                        player.write_log(f"ERR: Falha ao reabrir browser: {e}")
                    return

            try:
                with get_db_lock():
                    active_leads = get_new_leads()
            except Exception as e:
                print(f"[WhatsApp] CRM read error: {e}")
                await asyncio.sleep(30)
                cycle_count += 1
                continue

            if not active_leads:
                if player:
                    player.write_log(f"SYS: Todos os leads prospectados! Stats: {stats['enviadas']} enviadas, {stats['respondidas']} respondidas, {stats['invalidos']} inválidos, {stats['erros']} erros.")
                await asyncio.sleep(30)
                cycle_count += 1
                continue

            if player:
                player.write_log(f"SYS: {len(active_leads)} novos leads na fila!")

            leads_processed = 0
            for lead in active_leads:
                if self._stop or leads_processed >= max_leads_per_cycle:
                    break

                lead_name = lead.get("title", "Cliente")
                raw_phone = lead.get("phoneUnformatted", "")
                lead_phone = _normalize_phone(raw_phone)

                if not lead_phone or len(lead_phone) < 10:
                    stats["pulos"] += 1
                    if player:
                        player.write_log(f"SYS: Lead {lead_name} sem telefone válido. Pulando...")
                    try:
                        with get_db_lock():
                            mark_as_used(raw_phone)
                    except Exception:
                        mark_as_used(raw_phone)
                    continue

                if player:
                    player.write_log(f"SYS: ({leads_processed+1}/{len(active_leads)}) {lead_name} ({lead_phone[-8:]})...")

                try:
                    await self.page.goto(f"https://web.whatsapp.com/send?phone={lead_phone}")

                    chat_loaded = False
                    invalid_detected = False
                    for attempt in range(20):
                        if self._stop:
                            break
                        await self.check_and_dismiss_popups()

                        input_box = await self.page.query_selector("footer div[contenteditable='true']")
                        if input_box:
                            chat_loaded = True
                            break

                        invalid_popup = await self.page.query_selector("div[role='dialog']")
                        if invalid_popup:
                            popup_text = await invalid_popup.inner_text()
                            if any(term in popup_text.lower() for term in ["inválido", "invalid", "não está no", "not on whatsapp"]):
                                invalid_detected = True
                                break

                        await asyncio.sleep(1)

                    if invalid_detected:
                        stats["invalidos"] += 1
                        if player:
                            player.write_log(f"SYS: Telefone inválido. Pulando...")
                        invalid_popup = await self.page.query_selector("div[role='dialog']")
                        if invalid_popup:
                            ok_btn = await invalid_popup.query_selector("button")
                            if ok_btn:
                                await ok_btn.click()
                        try:
                            with get_db_lock():
                                mark_as_used(raw_phone)
                        except Exception:
                            mark_as_used(raw_phone)
                        await asyncio.sleep(3)
                        continue

                    if not chat_loaded:
                        stats["erros"] += 1
                        if player:
                            player.write_log(f"SYS: Timeout ao abrir chat. Pulando...")
                        continue

                    msgs = await self.get_last_messages(limit=2)

                    if not msgs:
                        opening = script.get("opening_message", "Bom dia, preciso falar com o responsável pelo marketing ou pelo comercial — é sobre uma proposta de divulgação pra empresa.")
                        if player:
                            player.write_log(f"SYS: Enviando proposta...")

                        await self.send_message(opening)
                        stats["enviadas"] += 1

                        try:
                            with get_db_lock():
                                mark_as_used(raw_phone)
                        except Exception:
                            mark_as_used(raw_phone)

                        if player:
                            player.write_log(f"SYS: OK")

                    else:
                        last_message_container = await self.page.query_selector_all(".message-out, .message-in")
                        if last_message_container:
                            last_container = last_message_container[-1]
                            classes = await last_container.evaluate("el => el.className")

                            if "message-in" in classes:
                                stats["respondidas"] += 1
                                last_msg = msgs[-1]
                                if player:
                                    player.write_log(f"LEADS: Respondeu: '{last_msg[:40]}'")

                                reply = await self._generate_reply(last_msg, script)
                                await self.send_message(reply)
                                stats["enviadas"] += 1

                                if player:
                                    player.write_log(f"JARVIS: Respondido.")

                                try:
                                    from actions.notifier import notify_client_reply
                                    notify_client_reply(f"Lead {lead_name} respondeu: {last_msg}")
                                except Exception:
                                    pass

                                try:
                                    with get_db_lock():
                                        mark_as_used(raw_phone)
                                except Exception:
                                    mark_as_used(raw_phone)
                            else:
                                if player:
                                    player.write_log(f"SYS: Já foi contactado. Pulando...")
                                try:
                                    with get_db_lock():
                                        mark_as_used(raw_phone)
                                except Exception:
                                    mark_as_used(raw_phone)

                except Exception as e:
                    stats["erros"] += 1
                    print(f"[WhatsApp] Error processing lead {lead_name}: {e}")
                    if player:
                        player.write_log(f"ERR: {e}")

                leads_processed += 1
                await asyncio.sleep(random.uniform(8, 15))

            if player:
                player.write_log(f"SYS: Ciclo {cycle_count + 1} finalizado. Stats: {stats['enviadas']} enviadas, {stats['respondidas']} respostas, {stats['invalidos']} inválidos, {stats['erros']} erros.")
            await asyncio.sleep(random.uniform(25, 40))
            cycle_count += 1

        if player:
            player.write_log(f"SYS: Prospecção encerrada após {cycle_count} ciclos. Final: {stats}")

    async def _generate_reply(self, message, script):
        msg_lower = message.lower().strip()

        objection_map = {
            "nao_temos_interesse": ["não tenho interesse", "não temos interesse", "não quero", "sem interesse", "não obrigado", "não obrigada", "dispenso"],
            "ja_temos_agencia": ["já temos agência", "ja temos agencia", "já temos assessoria", "agência própria", "parceria fechada", "já trabalho com"],
            "preco_alto": ["caro", "preço alto", "valor alto", "fora do orçamento", "não posso pagar", "muito caro", "muito dinheiro", "sai caro"],
            "sem_verba_agora": ["agora não", "sem verba", "orçamento apertado", "mês que vem", "depois eu vejo", "num outro momento", "sem grana"],
            "preciso_consultar": ["preciso consultar", "tenho que ver com", "falar com o", "preciso perguntar", "sócio", "parceiro", "decisão em conjunto"],
            "manda_email": ["manda no email", "envia por email", "manda proposta", "orçamento por email", "enviar por email"],
            "nao_confio": ["não conheço", "nunca ouvi falar", "primeira vez", "desconhecido", "golpe", "não confio"],
            "ja_temos_fornecedor": ["já tenho fornecedor", "já temos fornecedor", "já fechei com", "já contratamos", "já tenho quem faz"],
        }

        for key, patterns in objection_map.items():
            if any(x in msg_lower for x in patterns):
                resposta = script.get("objection_handling", {}).get(key)
                if resposta:
                    return resposta

        fallbacks = {
            "nao_temos_interesse": "Sem problemas! Só queria deixar meu contato pra quando precisarem. Sucesso com a marca!",
            "ja_temos_agencia": "Show! Trabalho como braço de apoio pra agências também. Se um dia precisarem de reforço, é só chamar.",
            "preco_alto": "Entendo! Que tal testarmos com uma arte primeiro, sem compromisso? Se gostar, a gente ajusta um pacote sob medida.",
        }

        for key, patterns in objection_map.items():
            if any(x in msg_lower for x in patterns):
                return fallbacks.get(key, "Entendo. Se quiser ver uns exemplos depois, meu contato tá aqui. Valeu!")

        try:
            api_key = _get_api_key()
            client = genai.Client(api_key=api_key)

            history_context = ""
            if self._conversation_history:
                recent = self._conversation_history[-6:]
                history_lines = []
                for msg in recent:
                    role = "Você" if msg["role"] == "assistant" else "Cliente"
                    history_lines.append(f"{role}: {msg['content']}")
                history_context = "\nHistórico recente da conversa:\n" + "\n".join(history_lines) + "\n"

            product_name = script.get('metadata', {}).get('product', 'Layouts de Anúncios')
            base_price = script.get('metadata', {}).get('price', 'R$ 10/foto ou pacote 15 fotos por R$ 120')
            max_discount = script.get('metadata', {}).get('max_discount', '20%')

            urgency = script.get('urgency_triggers', {})
            scarcity_text = urgency.get('scarcity', '')
            social_proof_text = urgency.get('social_proof', '')

            prompt = f"""
            Você é um designer freelancer brasileiro conversando informalmente com um dono de loja de roupas no WhatsApp.

            Produto: {product_name}
            Preço Base: {base_price}
            Desconto Máx: {max_discount}

            CONTEXTO DO ROTEIRO:
            - Contraposta: "{script.get('counter_proposal', '')}"
            - Fechamento: "{script.get('closing_message', '')}"
            {history_context}

            Mensagem do cliente: "{message}"

            TÉCNICAS DE PERSUASÃO (use quando couber):
            1. ESCASSEZ: "{scarcity_text}" (use se o cliente demonstrar interesse mas hesitar)
            2. PROVA SOCIAL: "{social_proof_text}" (use se o cliente questionar resultado)
            3. RECIPROCIDADE: Ofereça algo pequeno de graça primeiro (dica, arte teste)
            4. ANCORAGEM: Sempre mostre o pacote cheio primeiro, depois a oferta menor
            5. AUTORIDADE: Cite resultados de marcas que já atendeu

            DIRETRIZES:
            1. Seja EXTREMAMENTE conciso (máximo 2 frases curtas)
            2. Tom casual: 'total', 'show', 'opa', 'blz', 'valeu', 'tranquilo'
            3. NUNCA use frases genéricas de IA tipo 'Com certeza!', 'Entendo perfeitamente.'
            4. Termine com pergunta curta que force resposta sim/não ou escolha
            5. Se hesitar no preço, ofereça teste pequeno primeiro (não desconto grande)
            6. Use o histórico pra não repetir informação
            7. Se for follow-up sem resposta, seja útil (dê um benefício novo)

            Responda APENAS a mensagem exata, sem aspas ou explicações.
            """

            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt
            )
            reply = response.text.strip()
            if reply.startswith('"') and reply.endswith('"'):
                reply = reply[1:-1].strip()
            return reply

        except Exception as e:
            print(f"[Gemini Negotiation Error] {e}. Usando fallback...")
            return "Entendo. Se quiser, posso te mandar exemplos de edições que já fiz. Trabalho com R$ 10 por foto ou pacote de 15 por R$ 120. O que acha?"

async def _run_whatsapp_action(parameters, player):
    action = parameters.get("action")
    target = parameters.get("target")
    message = parameters.get("message")
    product = parameters.get("product")

    wa = WhatsAppWeb()
    try:
        await wa.start()
        if action == "send":
            await wa.open_chat(target)
            await wa.send_message(message)
            return f"Message sent to {target}."

        elif action == "autonomous":
            if target == "leads_results" or not target:
                await wa.multi_autonomous_loop(product, player)
            else:
                await wa.open_chat(target)
                await wa.autonomous_loop(product, player)
            return "Autonomous loop finished."

        elif action == "guard":
            timeout = parameters.get("timeout_minutes", 60)
            product = parameters.get("product")
            await wa.open_chat(target)
            await wa.guard_loop(target, message=message, player=player, timeout_minutes=timeout, product_name=product)
            return f"Guard mode ended for {target}."
    except asyncio.CancelledError:
        print("[WhatsApp] Action cancelled by user.")
        return "WhatsApp action cancelled."
    finally:
        wa._stop = True
        wa._stop_event.set()
        await wa.stop()

def whatsapp_web_action(parameters, player=None):
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run_whatsapp_action(parameters, player))
    except Exception as e:
        return f"WhatsApp error: {e}"
    finally:
        try:
            loop.close()
        except Exception:
            pass
