import os
import re
import asyncio
import json
import time
from pathlib import Path
from playwright.async_api import async_playwright
from google import genai
from google.genai import types

def get_base_dir():
    return Path(__file__).resolve().parent.parent

BASE_DIR = get_base_dir()
API_CONFIG_PATH = BASE_DIR / "config" / "api_keys.json"

def _get_api_key() -> str:
    with open(API_CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)["gemini_api_key"]

def _normalize_phone(phone_str: str) -> str:
    # Keep only digits
    digits = "".join(c for c in phone_str if c.isdigit())
    if not digits:
        return ""
    
    # Brazilian specific normalization
    # If it's a 10 or 11 digit number (e.g., 11987654321), prepend 55 (Brazil country code)
    if len(digits) in (10, 11) and not digits.startswith("55"):
        digits = "55" + digits
    return digits

class WhatsAppWeb:
    def __init__(self):
        self.browser = None
        self.context = None
        self.page = None
        self.playwright = None

    async def check_and_dismiss_popups(self):
        """Checks for common WhatsApp Web blocker popups and clicks the appropriate button."""
        try:
            # 1. Look for "Usar nesta janela" / "Usar aqui" (Use here) blocker popup
            for text in ["Usar nesta janela", "Usar aqui", "Use here", "usar nesta janela", "usar aqui", "use here"]:
                locator = self.page.get_by_text(re.compile(text, re.IGNORECASE))
                count = await locator.count()
                for i in range(count):
                    el = locator.nth(i)
                    try:
                        if await el.is_visible():
                            print(f"[WhatsApp] Found blocker element with text '{text}'. Clicking...")
                            await el.click(force=True)  # Force click just in case
                            await asyncio.sleep(2)
                            return
                    except Exception as click_err:
                        print(f"[WhatsApp] Click error on '{text}': {click_err}")
                        
            # 2. Selector fallback for "Usar nesta janela"
            for text in ["Usar nesta janela", "Usar aqui", "Use here"]:
                for selector in ["button", "div[role='button']", "span", "div"]:
                    locs = self.page.locator(f"{selector}:has-text('{text}')")
                    count = await locs.count()
                    for i in range(count):
                        btn = locs.nth(i)
                        try:
                            if await btn.is_visible():
                                print(f"[WhatsApp] Found blocker element via selector '{selector}' with text '{text}'. Clicking...")
                                await btn.click(force=True)
                                await asyncio.sleep(2)
                                return
                        except Exception as click_err:
                            print(f"[WhatsApp] Click error on '{selector}:{text}': {click_err}")

            # 3. Look for "O número ... não está no WhatsApp" or "invalid" popup
            dialogs = self.page.locator("div[role='dialog'], div[role='alertdialog']")
            dialog_count = await dialogs.count()
            for i in range(dialog_count):
                dialog = dialogs.nth(i)
                try:
                    if await dialog.is_visible():
                        text_content = await dialog.inner_text()
                        low_text = text_content.lower()
                        # Check if it's an invalid number popup (Portuguese and English)
                        if any(term in low_text for term in ["não está no whatsapp", "não está", "is not on whatsapp", "inválido", "invalid"]):
                            print(f"[WhatsApp] Detected invalid number popup: '{text_content.strip()}'. Clicking OK...")
                            # Find the OK button inside the dialog
                            ok_btn = dialog.get_by_text(re.compile("^OK$", re.IGNORECASE))
                            if await ok_btn.count() > 0:
                                await ok_btn.first.click(force=True)
                                await asyncio.sleep(1)
                                raise ValueError(f"PHONE_INVALID: {text_content.strip()}")
                except ValueError:
                    raise
                except Exception as dialog_err:
                    print(f"[WhatsApp] Error checking dialog content: {dialog_err}")
        except ValueError:
            raise
        except Exception as e:
            print(f"[WhatsApp] Error checking/dismissing popups: {e}")

    async def start(self):
        self.playwright = await async_playwright().start()
        
        # Path to Brave user data on Windows - USING A DEDICATED JARVIS PROFILE
        user_data_dir = os.path.join(os.environ["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "JarvisProfile")
        
        # Try to find Brave executable
        brave_path = os.path.join(os.environ["PROGRAMFILES"], "BraveSoftware", "Brave-Browser", "Application", "brave.exe")
        if not os.path.exists(brave_path):
            brave_path = os.path.join(os.environ["LOCALAPPDATA"], "BraveSoftware", "Brave-Browser", "Application", "brave.exe")

        try:
            self.context = await self.playwright.chromium.launch_persistent_context(
                user_data_dir,
                executable_path=brave_path if os.path.exists(brave_path) else None,
                headless=False,
                args=["--remote-debugging-port=9222"]
            )
        except Exception as launch_err:
            print(f"[WhatsApp] Persistent launch failed: {launch_err}. Trying fallback temporary profile...")
            # Fallback to a temporary profile to avoid blockages when Brave is already open
            import tempfile
            import random
            temp_profile = os.path.join(tempfile.gettempdir(), f"jarvis_temp_profile_{random.randint(1000, 9999)}")
            self.context = await self.playwright.chromium.launch_persistent_context(
                temp_profile,
                executable_path=brave_path if os.path.exists(brave_path) else None,
                headless=False,
                args=[] # No port to avoid conflicts
            )

        try:
            # Persistent context restores previous tabs. Reuse them to avoid duplicates.
            if self.context.pages:
                self.page = self.context.pages[-1]
                # Optional: close extra orphan tabs
                for p in self.context.pages[:-1]:
                    await p.close()
            else:
                self.page = await self.context.new_page()
                
            await self.page.goto("https://web.whatsapp.com")
            print("[WhatsApp] Browser started and navigated to WhatsApp Web.")
            
            # Active check for "Usar aqui" popup during initial load
            for _ in range(15):
                await self.check_and_dismiss_popups()
                await asyncio.sleep(1)
        except Exception as e:
            print(f"[WhatsApp] Error starting browser/page: {e}")
            await self.stop()
            raise

    async def stop(self):
        if self.context:
            await self.context.close()
        if self.playwright:
            await self.playwright.stop()

    async def open_chat(self, name_or_number):
        # Clean target to check if it's a phone number
        clean_num = _normalize_phone(name_or_number)
        is_phone = clean_num.isdigit() and len(clean_num) >= 8
        
        if is_phone:
            print(f"[WhatsApp] Target looks like a phone number. Opening direct chat link for: {clean_num}")
            await self.page.goto(f"https://web.whatsapp.com/send?phone={clean_num}")
            # Wait up to 15 seconds for chat loading, checking for popup
            for _ in range(15):
                await self.check_and_dismiss_popups()
                await asyncio.sleep(1)
            return

        # Search for contact using resilient selectors
        search_box = self.page.locator("div[contenteditable='true'][data-tab='3'], [placeholder='Pesquisar ou começar uma nova conversa']")
        
        # Wait up to 120 seconds with active popup check
        for _ in range(120):
            await self.check_and_dismiss_popups()
            try:
                if await search_box.is_visible():
                    break
            except:
                pass
            await asyncio.sleep(1)
            
        await search_box.click()
        await search_box.fill("")
        await search_box.type(name_or_number)
        await asyncio.sleep(2)
        
        # Click the first result
        chat_selector = f"span[title='{name_or_number}']"
        try:
            await self.page.click(chat_selector, timeout=5000)
        except:
            # Fallback to general chat list item if title match fails
            await self.page.keyboard.press("Enter")
        
        await asyncio.sleep(1)
    async def send_message(self, message):
        import random
        input_box = await self.page.wait_for_selector("footer div[contenteditable='true']")
        await input_box.click()
        
        # Simula digitação humana caractere por caractere para aparecer as bolinhas "digitando..."
        for char in message:
            await self.page.keyboard.type(char)
            await asyncio.sleep(random.uniform(0.015, 0.05)) # Atraso natural por tecla
            
        # Pequena pausa reflexiva antes de dar o enter
        await asyncio.sleep(random.uniform(0.4, 0.9))
        await self.page.keyboard.press("Enter")
        await asyncio.sleep(0.5)
        
        # Fallback explícito: se o botão de enviar ainda estiver visível, clica nele!
        try:
            send_btn = await self.page.query_selector("span[data-icon='send']")
            if send_btn:
                await send_btn.click()
        except:
            pass

    async def get_last_messages(self, limit=5):
        # Select message containers
        messages = await self.page.query_selector_all(".message-in")
        results = []
        for msg in messages[-limit:]:
            text = await msg.inner_text()
            if text:
                lines = text.strip().split("\n")
                if len(lines) > 1 and ("AM" in lines[-1] or "PM" in lines[-1] or ":" in lines[-1]):
                    text = "\n".join(lines[:-1])
                results.append(text.strip())
        return results

    async def autonomous_loop(self, product_name, player=None):
        from actions.negotiation_script import load_script
        script = load_script(product_name)
        if not script:
            print(f"[WhatsApp] No script found for {product_name}")
            if player:
                player.write_log(f"ERR: Nenhum roteiro encontrado para '{product_name}'")
            return

        if player:
            player.write_log(f"SYS: Iniciando fluxo de negociação para '{product_name}'...")
        
        # Envia a mensagem padrão inicial com digitação humana simulada
        opening = script.get("opening_message", "Bom dia, preciso falar com o responsável pelo marketing ou pelo comercial — é sobre uma proposta de divulgação pra empresa.")
        if player:
            player.write_log(f"SYS: Enviando mensagem padrão de contato inicial...")
            
        try:
            await self.send_message(opening)
            if player:
                player.write_log(f"SYS: Mensagem inicial enviada! Aguardando respostas do lead...")
        except Exception as e:
            print(f"[WhatsApp] Error sending opening message: {e}")
            if player:
                player.write_log(f"ERR: Falha ao enviar mensagem inicial: {e}")

        last_seen_msg = None
        
        while True:
            try:
                msgs = await self.get_last_messages(limit=1)
                if msgs and msgs[-1] != last_seen_msg:
                    incoming = msgs[-1]
                    last_seen_msg = incoming
                    print(f"[WhatsApp] New message: {incoming}")
                    if player:
                        player.write_log(f"LEADS: Nova mensagem de {incoming[:20]}...")
                    
                    # Call Gemini to generate reply
                    reply = await self._generate_reply(incoming, script)
                    print(f"[WhatsApp] Replying: {reply}")
                    
                    if player:
                        player.write_log(f"JARVIS: Digitando resposta humana...")
                    
                    await self.send_message(reply)
                    
                    if player:
                        player.write_log(f"JARVIS: Resposta enviada com sucesso.")
                    
                    # Trigger notification
                    from actions.notifier import notify_client_reply
                    notify_client_reply(incoming)
                
                await asyncio.sleep(5)
            except Exception as e:
                print(f"[WhatsApp] Loop error: {e}")
                await asyncio.sleep(10)

    async def multi_autonomous_loop(self, product_name, player=None):
        from actions.negotiation_script import load_script
        script = load_script(product_name)
        if not script:
            print(f"[WhatsApp] No script found for {product_name}")
            if player:
                player.write_log(f"ERR: Nenhum roteiro encontrado para '{product_name}'")
            return

        # Sincroniza qualquer lead de leads_results.json no banco de dados primeiro
        leads_path = get_base_dir() / "leads_results.json"
        if leads_path.exists():
            try:
                with open(leads_path, "r", encoding="utf-8") as f:
                    raw_leads = json.load(f)
                from actions.leads_manager import import_scraped_leads
                import_scraped_leads(raw_leads)
            except Exception as e:
                print(f"[WhatsApp CRM Sync] Sync failed: {e}")

        from actions.leads_manager import get_new_leads, mark_as_used

        if player:
            player.write_log("SYS: Iniciando prospecção inteligente com base no banco de leads (Novos vs Já Usados)...")

        while True:
            # Recarrega a lista de leads novos a cada loop para pegar novos leads minerados em tempo real!
            active_leads = get_new_leads()
            
            if not active_leads:
                if player:
                    player.write_log("SYS: Todos os leads foram prospectados! Aguardando novos leads serem minerados...")
                await asyncio.sleep(30)
                continue

            if player:
                player.write_log(f"SYS: {len(active_leads)} novos leads encontrados na fila para prospecção!")

            for lead in active_leads:
                lead_name = lead.get("title", "Cliente")
                raw_phone = lead.get("phoneUnformatted", "")
                
                # Clean and normalize phone prefix
                lead_phone = _normalize_phone(raw_phone)
                
                if not lead_phone:
                    if player:
                        player.write_log(f"SYS: Lead {lead_name} não possui telefone válido. Pulando e marcando como usado...")
                    mark_as_used(raw_phone)
                    continue

                if player:
                    player.write_log(f"SYS: Abrindo ligação direta via API para: {lead_name} (55{lead_phone[-10:] if len(lead_phone) >= 10 else lead_phone})...")
                
                try:
                    # Abre o chat diretamente pelo link do telefone LIMPO (sem "+"!)
                    await self.page.goto(f"https://web.whatsapp.com/send?phone={lead_phone}")
                    
                    # Aguarda o carregamento ativamente descartando quaisquer bloqueios ("Usar aqui", etc.)
                    for _ in range(8):
                        await self.check_and_dismiss_popups()
                        await asyncio.sleep(1)
                    
                    # Verifica se o chat abriu com sucesso ou se deu número inválido
                    invalid_popup = await self.page.query_selector("div[role='dialog']")
                    if invalid_popup:
                        popup_text = await invalid_popup.inner_text()
                        if any(term in popup_text.lower() for term in ["inválido", "invalid", "não está no", "not on whatsapp"]):
                            if player:
                                player.write_log(f"SYS: Lead {lead_name} possui telefone inválido no WhatsApp. Pulando...")
                            ok_btn = await invalid_popup.query_selector("button")
                            if ok_btn:
                                await ok_btn.click()
                            mark_as_used(raw_phone)
                            continue

                    # Lê as últimas mensagens do chat
                    msgs = await self.get_last_messages(limit=1)
                    
                    if not msgs:
                        # Chat fresco! Nunca enviamos nada. Envia a mensagem padrão inicial
                        opening = script.get("opening_message", "Bom dia, preciso falar com o responsável pelo marketing ou pelo comercial — é sobre uma proposta de divulgação pra empresa.")
                        if player:
                            player.write_log(f"SYS: Chat limpo! Enviando proposta padrão inicial para {lead_name}...")
                        
                        await self.send_message(opening)
                        
                        # Sucesso! Marca como USADO no banco para nunca repetir o envio!
                        mark_as_used(raw_phone)
                        if player:
                            player.write_log(f"SYS: Lead {lead_name} prospectado com sucesso e marcado como USADO.")
                        
                    else:
                        # Já conversamos com esse lead ou ele já respondeu. Marca como usado para liberar a fila.
                        mark_as_used(raw_phone)
                        last_msg = msgs[-1]
                        
                        # Verifica se a última mensagem é dele ou nossa
                        last_message_container = await self.page.query_selector_all(".message-out, .message-in")
                        if last_message_container:
                            last_container = last_message_container[-1]
                            classes = await last_container.evaluate("el => el.className")
                            
                            if "message-in" in classes:
                                # Significa que o cliente respondeu! O Jarvis assume a negociação!
                                if player:
                                    player.write_log(f"LEADS: {lead_name} respondeu: '{last_msg[:30]}...'")
                                    player.write_log(f"JARVIS: Formulando contraproposta curta e humana...")
                                
                                reply = await self._generate_reply(last_msg, script)
                                await self.send_message(reply)
                                
                                if player:
                                    player.write_log(f"JARVIS: Resposta de negociação enviada para {lead_name}.")
                                    
                                from actions.notifier import notify_client_reply
                                notify_client_reply(f"Lead {lead_name} respondeu: {last_msg}")
                            else:
                                if player:
                                    player.write_log(f"SYS: Aguardando retorno de {lead_name}...")
                                    
                except Exception as e:
                    print(f"[WhatsApp] Erro no processamento do lead {lead_name}: {e}")
                    if player:
                        player.write_log(f"ERR: Falha ao processar lead {lead_name}: {e}")
                
                await asyncio.sleep(5) # Pequeno intervalo de segurança entre leads
                
            if player:
                player.write_log("SYS: Ciclo completo finalizado. Aguardando 30 segundos para novas varreduras...")
            await asyncio.sleep(30)

    async def _generate_reply(self, message, script):
        import random
        
        msg_lower = message.lower().strip()
        
        # 1. INTENT ROUTING (Respostas Rápidas - Humanas e Curtas)
        # Desinteresse
        if any(x in msg_lower for x in ["não tenho interesse", "não temos interesse", "não quero", "sem interesse", "não obrigado", "não obrigada"]):
            return script.get("objection_handling", {}).get("nao_temos_interesse", "Sem problemas! Só queria deixar meu contato para o caso de precisarem no futuro. Valeu!")
            
        # Já temos agência
        if any(x in msg_lower for x in ["já temos agência", "ja temos agencia", "já temos assessoria", "agência própria", "parceria fechada"]):
            return script.get("objection_handling", {}).get("ja_temos_agencia", "Show! Trabalho muito como braço de apoio pra agências também. Se precisar de uma força com criativos rápidos, conta comigo.")

        # Preço alto
        if any(x in msg_lower for x in ["caro", "preço alto", "valor alto", "fora do orçamento", "não posso pagar"]):
            return script.get("objection_handling", {}).get("preco_alto", "Entendo total! Crio os layouts sob demanda e o retorno paga rápido. O que acha de testar uma única peça por R$ 120?")

        # 2. IA CLOSER DE NEGOCIAÇÃO (Gemini 2.0-Flash com o API Key existente)
        try:
            api_key = _get_api_key()
            client = genai.Client(api_key=api_key)
            
            prompt = f"""
            Você é um designer gráfico freelancer brasileiro conversando de forma informal e comercial com um possível cliente no WhatsApp.
            
            Objetivo: Negociar de forma natural e fechar o serviço de criação de anúncios de alta conversão.
            Produto: {script.get('metadata', {}).get('product', 'Layouts de Anúncios')}
            Preço Base: {script.get('metadata', {}).get('price', 'R$ 150')}
            Desconto Máximo Permitido: {script.get('metadata', {}).get('max_discount', '20%')}
            
            Roteiro da campanha:
            - Contraposta sugerida: "{script.get('counter_proposal', '')}"
            - Fechamento: "{script.get('closing_message', '')}"
            
            Mensagem recebida do cliente: "{message}"
            
            Diretrizes de Conversação Humana e Natural:
            1. Seja EXTREMAMENTE conciso. Máximo 1 ou 2 frases curtas. Mensagens grandes no WhatsApp parecem robóticas e cansam o cliente.
            2. Use tom de conversa brasileiro casual (por exemplo, use 'total', 'show', 'opa', 'blz', 'valeu').
            3. NUNCA use frases formais de IA como 'Com certeza!', 'Entendo perfeitamente.', 'Olá! Como posso te ajudar hoje?'.
            4. Se o cliente perguntar o preço, tente ancorar o valor de {script.get('metadata', {}).get('price', 'R$ 150')}, mas se ele chorar ou hesitar, aplique o desconto de até {script.get('metadata', {}).get('max_discount', '20%')} de forma natural.
            5. Sempre termine com uma pergunta curta que incentive a resposta, mantendo o fluxo da negociação.
            
            Responda APENAS com a mensagem exata para enviar no WhatsApp, sem aspas, comentários ou explicações.
            """
            
            response = client.models.generate_content(
                model="gemini-2.0-flash",
                contents=prompt
            )
            reply = response.text.strip()
            reply = reply.replace('"', '').strip()
            return reply
            
        except Exception as e:
            print(f"[Gemini Negotiation Error] {e}. Usando fallback local...")
            return "Entendo total. Se quiser ver uns exemplos rápidos de anúncios que já criei para lojas parecidas, posso te mandar por aqui. O que acha?"
def whatsapp_web_action(parameters, player=None):
    action = parameters.get("action")
    target = parameters.get("target") # Name or number
    message = parameters.get("message")
    product = parameters.get("product")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    wa = WhatsAppWeb()
    
    try:
        if action == "send":
            loop.run_until_complete(wa.start())
            loop.run_until_complete(wa.open_chat(target))
            loop.run_until_complete(wa.send_message(message))
            return f"Message sent to {target}."
            
        elif action == "autonomous":
            loop.run_until_complete(wa.start())
            if target == "leads_results" or not target:
                loop.run_until_complete(wa.multi_autonomous_loop(product, player))
            else:
                loop.run_until_complete(wa.open_chat(target))
                loop.run_until_complete(wa.autonomous_loop(product, player))
            return "Autonomous loop finished."
            
    except Exception as e:
        return f"WhatsApp error: {e}"
    finally:
        loop.run_until_complete(wa.stop())
        loop.close()
