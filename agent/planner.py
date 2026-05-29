import json
import re


PLANNER_PROMPT = """You are the planning module of MARK XXV, a personal AI assistant.
Your job: break any user goal into a sequence of steps using ONLY the tools listed below.

ABSOLUTE RULES:
- NEVER use generated_code or write Python scripts. It does not exist.
- NEVER reference previous step results in parameters. Every step is independent.
- Use web_search for ANY information retrieval, research, or current data.
- Use file_controller to save content to disk.
- Max 5 steps. Use the minimum steps needed.

AVAILABLE TOOLS AND THEIR PARAMETERS:

open_app
  app_name: string (required) — name of the LOCAL desktop application (e.g. "Claude", "Spotify", "Brave")
  play: boolean (optional) — if true, attempts to play media after opening
  query: string (optional) — specific song or item to search and play (use for Spotify)

manage_memory
  action: string (required) — store | retrieve | get_all
  key: string (optional) — the fact key (e.g. "user_name")
  value: string (optional) — the fact value to store

ALWAYS use the Brave browser for any web tasks. Never use Edge or Chrome.

web_search
  query: string (required) — write a clear, focused search query
  mode: "search" or "compare" (optional, default: search)
  items: list of strings (optional, for compare mode)
  aspect: string (optional, for compare mode)

game_updater
  action: "update" | "install" | "list" | "download_status" | "schedule" (required)
  platform: "steam" | "epic" | "both" (optional, default: both)
  game_name: string (optional)
  app_id: string (optional)
  shutdown_when_done: boolean (optional)

browser_control
  action: "go_to" | "search" | "click" | "type" | "scroll" | "get_text" | "press" | "close" (required)
  url: string (for go_to)
  query: string (for search)
  text: string (for click/type)
  direction: "up" | "down" (for scroll)

file_controller
  action: "write" | "create_file" | "read" | "list" | "delete" | "move" | "copy" | "find" | "disk_usage" (required)
  path: string — use "desktop" for Desktop folder
  name: string — filename
  content: string — file content (for write/create_file)

computer_settings
  action: string (required)
  description: string — natural language description
  value: string (optional)

computer_control
  action: "type" | "click" | "hotkey" | "press" | "scroll" | "screenshot" | "screen_find" | "screen_click" (required)
  text: string (for type)
  x, y: int (for click)
  keys: string (for hotkey, e.g. "ctrl+c")
  key: string (for press)
  direction: "up" | "down" (for scroll)
  description: string (for screen_find/screen_click)

screen_process
  text: string (required) — what to analyze or ask about the screen
  angle: "screen" | "camera" (optional)

send_message
  receiver: string (required)
  message_text: string (required)
  platform: string (required)

reminder
  date: string YYYY-MM-DD (required)
  time: string HH:MM (required)
  message: string (required)

desktop_control
  action: "wallpaper" | "organize" | "clean" | "list" | "task" (required)
  path: string (optional)
  task: string (optional)

youtube_video
  action: "play" | "summarize" | "trending" (required)
  query: string (for play)

weather_report
  city: string (required)

flight_finder
  origin: string (required)
  destination: string (required)
  date: string (required)

code_helper
  action: "write" | "edit" | "run" | "explain" (required)
  description: string (required)
  language: string (optional)
  output_path: string (optional)
  file_path: string (optional)
  
apify_leads
  actor_id: string (required) — e.g. "compass/crawler-google-places"
  input_data: object (required) — parameters like searchStringsArray or directUrls
  
whatsapp_web
  action: "send" | "autonomous" | "guard" (required)
  target: string (required) — contact or phone or "leads_results"
  message: string (for 'send' or 'guard')
  product: string (for 'autonomous')
  timeout_minutes: integer (for 'guard' — default: 60)

negotiation_script
  action: "generate" | "load" (required)
  product: string (required)
  price: string (optional)
  max_discount: string (optional)
  tone: string (optional)

dev_agent
  description: string (required)
  language: string (optional)

self_repair
  No parameters. Runs self-diagnostics and auto-repair on the assistant's codebase.

manage_crm
  action: "stats" | "list" | "get" | "mark_used" | "delete" | "clear" (required)
  query: string (for list/get — search by name, phone, or category)
  status: "new" | "used" | "all" (for list/clear — default: new)
  limit: integer (for list — max results, default: 10)
  phone: string (for mark_used/delete — phone number)

refresh_geopolitics
  No parameters. Fetches real-time global news, market tickers, and threat level via Google Search.

EXAMPLES:

Goal: "research mechanical engineering and save it to a notepad file"
Steps:

web_search | query: "mechanical engineering overview definition history"
web_search | query: "mechanical engineering applications and future trends"
file_controller | action: write, path: desktop, name: mechanical_engineering.txt, content: "MECHANICAL ENGINEERING RESEARCH\n\nThis file will be filled with web research results."

Goal: "What is the price of Bitcoin"
Steps:

web_search | query: "Bitcoin price today USD"

Goal: "List the files on the desktop and find the largest 5 files"
Steps:

file_controller | action: list, path: desktop
file_controller | action: largest, path: desktop, count: 5

Goal: "Install PUBG from Steam"
Steps:

game_updater | action: install, platform: steam, game_name: "PUBG"

Goal: "Update all my Steam games"
Steps:

game_updater | action: update, platform: steam

Goal: "Send John a message on WhatsApp saying there is a meeting tomorrow"
Steps:

whatsapp_web | action: "send", target: "John", message: "There is a meeting tomorrow"

Goal: "Open the clock and set a reminder for 30 minutes later"
Steps:

reminder | date: [today], time: [now+30min], message: "Reminder"

Goal: "use o apify encontre 50 leads de lojas de roupa e envie mensagem para eles"
Steps:

apify_leads | actor_id: "compass/crawler-google-places", input_data: {"searchStringsArray": ["lojas de roupa em São Paulo"], "maxResults": 50}
whatsapp_web | action: "autonomous", target: "leads_results", product: "Criativos de Moda Streetwear"

OUTPUT — return ONLY valid JSON, no markdown, no explanation, no code blocks:
{
  "goal": "...",
  "steps": [
    {
      "step": 1,
      "tool": "tool_name",
      "description": "what this step does",
      "parameters": {},
      "critical": true
    }
  ]
}
"""


from core.utils import get_api_key as _get_api_key


def create_plan(goal: str, context: str = "") -> dict:
    import agent.local_genai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash-lite",
        system_instruction=PLANNER_PROMPT
    )

    user_input = f"Goal: {goal}"
    if context:
        user_input += f"\n\nContext: {context}"

    try:
        response = model.generate_content(user_input)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()

        plan = json.loads(text)

        if "steps" not in plan or not isinstance(plan["steps"], list):
            raise ValueError("Invalid plan structure")

        for step in plan["steps"]:
            if step.get("tool") in ("generated_code",):
                print(f"[Planner] [WARNING] generated_code detected in step {step.get('step')} - replacing with web_search")
                desc = step.get("description", goal)
                step["tool"] = "web_search"
                step["parameters"] = {"query": desc[:200]}

        print(f"[Planner] [SUCCESS] Plan: {len(plan['steps'])} steps")
        for s in plan["steps"]:
            print(f"  Step {s['step']}: [{s['tool']}] {s['description']}")

        return plan

    except json.JSONDecodeError as e:
        print(f"[Planner] [ERROR] JSON parse failed: {e}")
        return _fallback_plan(goal)
    except Exception as e:
        print(f"[Planner] [ERROR] Planning failed: {e}")
        return _fallback_plan(goal)


def _fallback_plan(goal: str) -> dict:
    """Fallback when JSON planning fails. Uses keyword matching to map intent to tools."""
    goal_lower = goal.lower().strip().strip(",.!?;:")
    print(f"[Planner] [FALLBACK] Attempting intent match for: {goal[:80]}")

    # ── Tool intents ──
    intent_map = [
        # open_app
        (r'(abr[aeiir]+|open|lanc[aeiir]+|execut[aeiir]+|inici[aeiir]+)',
         lambda: ("open_app", {"app_name": _extract_app_name(goal)})),

        # web_search — anything asking for info, news, analysis, research
        (r'(pesquis[aeiir]+|busca[rz]|procur[aeiir]+|google|search|pesquisa|'
         r'an[áa]lis[aeiir]+|analise|analis[aeiir]+|o\s+que\s+[ée]\s+|'
         r'me\s+diga\s+sobre|me\s+fale\s+sobre|sobre\s+|'
         r'not[íi]cias?|[uú]ltimas\s+not[íi]cias|novidades?\s+sobre|'
         r'quero\s+saber\s+sobre|preciso\s+de\s+informa[cç][ãa]o|'
         r'qual\s+[aá]\s+situa[cç][ãa]o|como\s+est[áa]\s+|'
         r'explique|explique\s+sobre|conte\s+mais\s+sobre|'
         r'inform[aeiç]+[oõ]es?\s+sobre|dados\s+sobre)',
         lambda: ("web_search", {"query": goal})),

        # whatsapp
        (r'(whatsapp|whats\s*app|mensagem|enviar\s+mensagem|mandar\s+mensagem)',
         lambda: ("whatsapp_web", {"action": "send", "target": "lead", "message": goal})),

        # reminder / alarm
        (r'(lembrete|lembr[ae]|alarm[aei]|notific[ai]|despertador)',
         lambda: ("reminder", {"date": "", "time": "", "message": goal})),

        # weather
        (r'(clima|tempo|temperatura|previs[ãa]o\s+do\s+tempo)',
         lambda: ("weather_report", {"city": _extract_city(goal)})),

        # spotify / music
        (r'(m[uú]sica|spotify|toc[aeiir]+|play|can[cç][aã]o|som)',
         lambda: ("open_app", {"app_name": "Spotify", "play": True})),

        # file / save
        (r'(arquiv[ao]|salv[aeiir]+|documento|cri[aeiir]+\s+arquiv|[cr]ri[aeiir]+\s+documento)',
         lambda: ("file_controller", {"action": "write", "path": "desktop", "name": _extract_filename(goal), "content": goal})),

        # memory
        (r'(mem[óo]ria|lembr[ae]r\s+de|guarda[rz]|anot[aeiir]+)',
         lambda: ("manage_memory", {"action": "store", "key": goal[:30], "value": goal})),

        # game / steam
        (r'(jogo|game|steam|epic|atualiz[aeiir]+\s+jogos)',
         lambda: ("game_updater", {"action": "update", "platform": "both"})),

        # CRM / leads
        (r'(crm|lead|cliente|contato)',
         lambda: ("manage_crm", {"action": "list", "status": "new", "limit": 10})),

        # clock / time
        (r'(hor[áa]rio|rel[óo]gio|que\s+horas|hora\s+atual)',
         lambda: ("web_search", {"query": goal})),

        # computer settings
        (r'(configur[aeiir]+|ajust[aeiir]+|defini[cç][ãa]o|resolu[cç][ãa]o|brilho|volume|wifi|bluetooth)',
         lambda: ("computer_settings", {"action": "apply", "description": goal})),

        # browser control
        (r'(navegador|brave|site|p[aá]gina|url|acess[aeiir]+\s+o\s+site|entr[aeiir]+\s+no\s+site)',
         lambda: ("browser_control", {"action": "go_to", "url": _extract_url(goal)})),

        # screenshot
        (r'(print|screenshot|captur[aeiir]+\s+tela|foto\s+da\s+tela)',
         lambda: ("computer_control", {"action": "screenshot"})),

        # self repair
        (r'(diagn[óo]stico|repar[aeiir]+|auto\s+repar[aeiir]+|sa[uú]de\s+do\s+sistema|self\s+repair)',
         lambda: ("self_repair", {})),

        # geopolitics / news
        (r'(geopol[íi]tica|not[íi]cia|amea[cç]a|threat|news|mundo|global)',
         lambda: ("refresh_geopolitics", {})),

        # flight
        (r'(voo|flight|passagem|viagem|viaj[aeiir]+\s+de\s+avi[aã]o)',
         lambda: ("flight_finder", {"origin": "", "destination": "", "date": ""})),
    ]

    for pattern, builder in intent_map:
        if re.search(pattern, goal_lower):
            tool, params = builder()
            print(f"[Planner] [FALLBACK] Intent matched: {tool}")
            return {
                "goal": goal,
                "steps": [{
                    "step": 1, "tool": tool,
                    "description": f"{tool}: {goal[:80]}",
                    "parameters": params, "critical": True
                }]
            }

    # ── No tool matched → treat as conversation via LLM ──
    print(f"[Planner] [CONVERSATION] No tool matched, routing to chat: {goal[:80]}")
    return {
        "goal": goal,
        "steps": [{
            "step": 1, "tool": "conversation",
            "description": f"Conversar com JARVIS: {goal[:80]}",
            "parameters": {"user_message": goal, "response": ""},
"critical": False
        }]
    }


def _extract_app_name(goal: str) -> str:
    """Extract app name after 'abra'/'open' etc."""
    m = re.search(r'(?:abr[aeiir]+|open|lanc[aeiir]+|execut[aeiir]+|inici[aeiir]+)\s+(?:o\s+|a\s+|os\s+|as\s+)?(.+)', goal, re.IGNORECASE)
    if m:
        name = m.group(1).strip()
        known = {
            "brave": "Brave", "chrome": "Brave", "edge": "Brave", "navegador": "Brave",
            "spotify": "Spotify", "musica": "Spotify", "whatsapp": "WhatsApp",
            "calculadora": "Calculator", "calc": "Calculator",
            "bloco de notas": "Notepad", "notepad": "Notepad",
            "explorador de arquivos": "File Explorer", "explorer": "File Explorer",
            "terminal": "Windows Terminal", "cmd": "Windows Terminal", "prompt": "Windows Terminal",
            "discord": "Discord", "telegram": "Telegram",
            "vs code": "Code", "vscode": "Code", "visual studio": "Code",
            "word": "Microsoft Word", "excel": "Microsoft Excel", "powerpoint": "Microsoft PowerPoint",
            "outlook": "Microsoft Outlook", "office": "Microsoft Word",
            "configurações": "Settings", "settings": "Settings",
            "relógio": "Clock", "clock": "Clock",
        }
        for k, v in known.items():
            if k in name.lower():
                return v
        return name
    return goal[:30]


def _extract_city(goal: str) -> str:
    m = re.search(r'(?:em|de|do|da|para)\s+(.+?)(?:\s*[?.!]|$)', goal)
    return m.group(1).strip().capitalize() if m else "São Paulo"


def _extract_filename(goal: str) -> str:
    m = re.search(r'(?:salv[aeiir]+|cri[aeiir]+|arquiv[ao]|documento)\s+(?:para\s+|como\s+|em\s+)?(.+)', goal, re.IGNORECASE)
    if m:
        return m.group(1).strip()[:50] + ".txt"
    return "documento.txt"


def _extract_url(goal: str) -> str:
    m = re.search(r'(https?://[^\s]+)', goal)
    if m:
        return m.group(1)
    m2 = re.search(r'(?:acess[aeiir]+\s+o\s+site|entr[aeiir]+\s+em|site|acess[aeiir]+)\s+(.+?)(?:\s*[?.!]|$)', goal, re.IGNORECASE)
    if m2:
        site = m2.group(1).strip().lower()
        if not site.startswith("http"):
            return "https://" + site
        return site
    return "https://www.google.com"


def replan(goal: str, completed_steps: list, failed_step: dict, error: str) -> dict:
    import agent.local_genai as genai

    genai.configure(api_key=_get_api_key())
    model = genai.GenerativeModel(
        model_name="gemini-2.5-flash",
        system_instruction=PLANNER_PROMPT
    )

    completed_summary = "\n".join(
        f"  - Step {s['step']} ({s['tool']}): DONE" for s in completed_steps
    )

    prompt = f"""Goal: {goal}

Already completed:
{completed_summary if completed_summary else '  (none)'}

Failed step: [{failed_step.get('tool')}] {failed_step.get('description')}
Error: {error}

Create a REVISED plan for the remaining work only. Do not repeat completed steps."""

    try:
        response = model.generate_content(prompt)
        text     = response.text.strip()
        text     = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
        plan     = json.loads(text)

        for step in plan.get("steps", []):
            if step.get("tool") == "generated_code":
                step["tool"] = "web_search"
                step["parameters"] = {"query": step.get("description", goal)[:200]}

        print(f"[Planner] [REPLAN] Revised plan: {len(plan['steps'])} steps")
        return plan
    except Exception as e:
        print(f"[Planner] [ERROR] Replan failed: {e}")
        return _fallback_plan(goal)