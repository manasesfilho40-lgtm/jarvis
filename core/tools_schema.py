TOOL_DECLARATIONS = [
    {
        "name": "open_app",
        "description": "Opens any application on the computer.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "app_name": {
                    "type": "STRING",
                    "description": "App name (e.g. WhatsApp, Chrome, Spotify)"
                },
                "play": {"type": "BOOLEAN", "description": "Play media after opening"},
                "query": {"type": "STRING", "description": "Song or item to search and play"}
            },
            "required": ["app_name"]
        }
    },
    {
        "name": "web_search",
        "description": "Searches the web for any information.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":  {"type": "STRING", "description": "Search query"},
                "mode":   {"type": "STRING", "description": "search or compare"},
                "items":  {"type": "ARRAY", "items": {"type": "STRING"}, "description": "Items to compare"},
                "aspect": {"type": "STRING", "description": "price | specs | reviews"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "weather_report",
        "description": "Gets weather for a city.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "city": {"type": "STRING", "description": "City name"}
            },
            "required": ["city"]
        }
    },
    {
        "name": "send_message",
        "description": "Sends message via Telegram, Signal, Discord, Instagram, or Messenger. For WhatsApp use whatsapp_web tool.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "receiver":     {"type": "STRING", "description": "Recipient name"},
                "message_text": {"type": "STRING", "description": "Message text"},
                "platform":     {"type": "STRING", "description": "Telegram, Signal, Discord, Instagram, Messenger"}
            },
            "required": ["receiver", "message_text", "platform"]
        }
    },
    {
        "name": "reminder",
        "description": "Sets a timed reminder.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "date":    {"type": "STRING", "description": "YYYY-MM-DD"},
                "time":    {"type": "STRING", "description": "HH:MM (24h)"},
                "message": {"type": "STRING", "description": "Reminder text"}
            },
            "required": ["date", "time", "message"]
        }
    },
    {
        "name": "youtube_video",
        "description": "Controls YouTube: play, summarize, get info, trending.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "play | summarize | get_info | trending"},
                "query":  {"type": "STRING", "description": "Search query"},
                "save":   {"type": "BOOLEAN", "description": "Save summary to Notepad"},
                "region": {"type": "STRING", "description": "Country code e.g. TR, US"},
                "url":    {"type": "STRING", "description": "Video URL"},
            },
            "required": []
        }
    },
    {
        "name": "screen_process",
        "description": "Captures and analyzes screen or webcam. Call when user asks what you see.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "angle": {"type": "STRING", "description": "screen or camera"},
                "text":  {"type": "STRING", "description": "Question about the image"}
            },
            "required": ["text"]
        }
    },
    {
        "name": "computer_settings",
        "description": "Controls computer: volume, brightness, WiFi, sleep, etc.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "Action to perform"},
                "description": {"type": "STRING", "description": "Natural language description"},
                "value":       {"type": "STRING", "description": "Optional value"}
            },
            "required": []
        }
    },
    {
        "name": "browser_control",
        "description": "Controls any web browser: navigate, click, type, scroll, screenshot.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "go_to | search | click | type | scroll | fill_form | smart_click | smart_type | get_text | get_url | press | new_tab | close_tab | screenshot | back | forward | reload | switch | list_browsers | close | close_all"},
                "browser":     {"type": "STRING", "description": "brave | chrome | edge | firefox | opera | vivaldi"},
                "url":         {"type": "STRING", "description": "URL for go_to/new_tab"},
                "query":       {"type": "STRING", "description": "Search query"},
                "engine":      {"type": "STRING", "description": "google | bing | duckduckgo"},
                "selector":    {"type": "STRING", "description": "CSS selector"},
                "text":        {"type": "STRING", "description": "Text to click or type"},
                "description": {"type": "STRING", "description": "Element description for smart actions"},
                "direction":   {"type": "STRING", "description": "up | down"},
                "amount":      {"type": "INTEGER", "description": "Pixels to scroll"},
                "key":         {"type": "STRING", "description": "Key name e.g. Enter, F5"},
                "path":        {"type": "STRING", "description": "Screenshot save path"},
                "incognito":   {"type": "BOOLEAN", "description": "Private mode"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field before typing (default: true)"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "manage_memory",
        "description": "Stores/retrieves facts about the user.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "store | retrieve | get_all"},
                "key":    {"type": "STRING", "description": "Fact key e.g. favorite_color"},
                "value":  {"type": "STRING", "description": "Fact value"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "file_controller",
        "description": "Manages files: list, create, delete, move, copy, rename, read, write, find.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "list | create_file | create_folder | delete | move | copy | rename | read | write | find | largest | disk_usage | organize_desktop | info"},
                "path":        {"type": "STRING", "description": "Path or shortcut: desktop, downloads, documents"},
                "destination": {"type": "STRING", "description": "Destination for move/copy"},
                "new_name":    {"type": "STRING", "description": "New name for rename"},
                "content":     {"type": "STRING", "description": "Content for create_file/write"},
                "name":        {"type": "STRING", "description": "File name to find"},
                "extension":   {"type": "STRING", "description": "Extension e.g. .pdf"},
                "count":       {"type": "INTEGER", "description": "Results count"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "desktop_control",
        "description": "Controls desktop: wallpaper, organize, clean, list, stats.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "wallpaper | wallpaper_url | organize | clean | list | stats | task"},
                "path":   {"type": "STRING", "description": "Image path"},
                "url":    {"type": "STRING", "description": "Image URL"},
                "mode":   {"type": "STRING", "description": "by_type or by_date"},
                "task":   {"type": "STRING", "description": "Desktop task description"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "code_helper",
        "description": "Writes, edits, explains, runs, or builds code.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "write | edit | explain | run | build | auto"},
                "description": {"type": "STRING", "description": "What to do"},
                "language":    {"type": "STRING", "description": "Python (default)"},
                "output_path": {"type": "STRING", "description": "Save path"},
                "file_path":   {"type": "STRING", "description": "Existing file path"},
                "code":        {"type": "STRING", "description": "Raw code to explain"},
                "args":        {"type": "STRING", "description": "CLI arguments"},
                "timeout":     {"type": "INTEGER", "description": "Timeout in seconds"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "dev_agent",
        "description": "Builds multi-file projects from scratch.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "description":  {"type": "STRING", "description": "What to build"},
                "language":     {"type": "STRING", "description": "Python (default)"},
                "project_name": {"type": "STRING", "description": "Folder name"},
                "timeout":      {"type": "INTEGER", "description": "Timeout in seconds"},
            },
            "required": ["description"]
        }
    },
    {
        "name": "agent_task",
        "description": "Executes complex multi-step tasks requiring multiple tools.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "goal":     {"type": "STRING", "description": "What to accomplish"},
                "priority": {"type": "STRING", "description": "low | normal | high"}
            },
            "required": ["goal"]
        }
    },
    {
        "name": "computer_control",
        "description": "Direct computer control: type, click, hotkeys, scroll, mouse, screenshot.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":      {"type": "STRING", "description": "type | smart_type | click | double_click | right_click | hotkey | press | scroll | move | copy | paste | screenshot | wait | clear_field | focus_window | screen_find | screen_click | random_data | user_data"},
                "text":        {"type": "STRING", "description": "Text to type"},
                "x":           {"type": "INTEGER", "description": "X coordinate"},
                "y":           {"type": "INTEGER", "description": "Y coordinate"},
                "keys":        {"type": "STRING", "description": "e.g. ctrl+c"},
                "key":         {"type": "STRING", "description": "e.g. enter"},
                "direction":   {"type": "STRING", "description": "up | down | left | right"},
                "amount":      {"type": "INTEGER", "description": "Scroll amount"},
                "seconds":     {"type": "NUMBER",  "description": "Wait seconds"},
                "title":       {"type": "STRING",  "description": "Window title"},
                "description": {"type": "STRING",  "description": "Element description"},
                "type":        {"type": "STRING",  "description": "Data type for random_data"},
                "field":       {"type": "STRING",  "description": "name|email|city"},
                "clear_first": {"type": "BOOLEAN", "description": "Clear field first"},
                "path":        {"type": "STRING",  "description": "Screenshot path"},
            },
            "required": ["action"]
        }
    },
    {
        "name": "game_updater",
        "description": "Steam/Epic: install, update, list, schedule games.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action":    {"type": "STRING",  "description": "update | install | list | download_status | schedule | cancel_schedule | schedule_status"},
                "platform":  {"type": "STRING",  "description": "steam | epic | both"},
                "game_name": {"type": "STRING",  "description": "Game name"},
                "app_id":    {"type": "STRING",  "description": "Steam AppID"},
                "hour":      {"type": "INTEGER", "description": "Schedule hour 0-23"},
                "minute":    {"type": "INTEGER", "description": "Schedule minute 0-59"},
                "shutdown_when_done": {"type": "BOOLEAN", "description": "Shutdown PC when done"},
            },
            "required": []
        }
    },
    {
        "name": "flight_finder",
        "description": "Searches Google Flights for best options.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "origin":      {"type": "STRING",  "description": "Departure city or airport"},
                "destination": {"type": "STRING",  "description": "Arrival city or airport"},
                "date":        {"type": "STRING",  "description": "Departure date"},
                "return_date": {"type": "STRING",  "description": "Return date"},
                "passengers":  {"type": "INTEGER", "description": "Number of passengers"},
                "cabin":       {"type": "STRING",  "description": "economy | premium | business | first"},
                "save":        {"type": "BOOLEAN", "description": "Save to Notepad"},
            },
            "required": ["origin", "destination", "date"]
        }
    },
    {
        "name": "shutdown_jarvis",
        "description": "Shuts down JARVIS when user says goodbye.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
        }
    },
    {
        "name": "file_processor",
        "description": "Processes uploaded files: images, PDFs, docs, code, audio, video, archives.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "file_path": {"type": "STRING", "description": "File path. Leave empty for current file."},
                "action":    {"type": "STRING", "description": "describe | summarize | extract_text | resize | convert | transcribe | analyze | etc."},
                "instruction": {"type": "STRING", "description": "Free-form instruction if action doesn't cover it"},
                "format":    {"type": "STRING", "description": "Target format e.g. mp3, pdf, csv, png"},
                "width":     {"type": "INTEGER", "description": "Image width"},
                "height":    {"type": "INTEGER", "description": "Image height"},
                "scale":     {"type": "NUMBER",  "description": "Scale factor"},
                "quality":   {"type": "INTEGER", "description": "Quality 1-100"},
                "start":     {"type": "STRING",  "description": "Start time for trim"},
                "end":       {"type": "STRING",  "description": "End time for trim"},
                "timestamp": {"type": "STRING",  "description": "Frame timestamp"},
                "column":    {"type": "STRING",  "description": "CSV column name"},
                "value":     {"type": "STRING",  "description": "Filter value"},
                "condition": {"type": "STRING",  "description": "equals|contains|gt|lt"},
                "ascending": {"type": "BOOLEAN", "description": "Sort ascending"},
                "save":      {"type": "BOOLEAN", "description": "Save result to file"},
                "destination": {"type": "STRING", "description": "Output folder"},
            },
            "required": []
        }
    },
    {
        "name": "save_memory",
        "description": "Saves personal facts about the user silently.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "category": {"type": "STRING", "description": "identity | preferences | projects | relationships | wishes | notes"},
                "key":   {"type": "STRING", "description": "snake_case key (e.g. favorite_food)"},
                "value": {"type": "STRING", "description": "Value in English"},
            },
            "required": ["category", "key", "value"]
        }
    },
    {
        "name": "apify_leads",
        "description": "Scrapes leads using Apify actors (Google Places, Instagram, Facebook).",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "actor_id": {"type": "STRING", "description": "Apify Actor ID"},
                "input_data": {
                    "type": "OBJECT",
                    "properties": {
                        "searchStringsArray": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "searchQueries": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "directUrls": {"type": "ARRAY", "items": {"type": "STRING"}},
                        "maxResults": {"type": "INTEGER"}
                    },
                    "description": "Input parameters with correct technical field names"
                }
            },
            "required": ["actor_id", "input_data"]
        }
    },
    {
        "name": "whatsapp_web",
        "description": "All WhatsApp operations: send, guard, autonomous sales.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "send | autonomous | guard"},
                "target": {"type": "STRING", "description": "Contact name or phone with country code"},
                "message": {"type": "STRING", "description": "Message text"},
                "product": {"type": "STRING", "description": "Product name for autonomous/guard mode"},
                "timeout_minutes": {"type": "INTEGER", "description": "Guard mode timeout"}
            },
            "required": ["action", "target"]
        }
    },
    {
        "name": "negotiation_script",
        "description": "Generates or loads a sales negotiation script.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "generate | load"},
                "product": {"type": "STRING", "description": "Product name"},
                "price": {"type": "STRING", "description": "Price"},
                "max_discount": {"type": "STRING", "description": "Max discount"},
                "tone": {"type": "STRING", "description": "formal | casual | aggressive | consultative"}
            },
            "required": ["action", "product"]
        }
    },
    {
        "name": "notifier",
        "description": "Sends desktop notification with sound.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "title": {"type": "STRING", "description": "Title"},
                "message": {"type": "STRING", "description": "Body text"}
            },
            "required": ["message"]
        }
    },
    {
        "name": "self_repair",
        "description": "Diagnoses and repairs Jarvis system issues.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "manage_crm",
        "description": "Manages leads CRM: stats, list, get, mark_used, delete, clear.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "stats | list | get | mark_used | delete | clear"},
                "query":  {"type": "STRING", "description": "Search term for list/get"},
                "status": {"type": "STRING", "description": "new | used | all"},
                "limit":  {"type": "INTEGER", "description": "Max results"},
                "phone":  {"type": "STRING", "description": "Phone for mark_used/delete"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "refresh_geopolitics",
        "description": "Fetches latest geopolitical news, markets, and threat level via Google Search.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "night_mode",
        "description": "Controls Night Mode. When active, JARVIS fica em silêncio e só interrompe pra emergências.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "on | off | schedule"},
                "hour":   {"type": "INTEGER", "description": "Hour to auto-activate (0-23), only for schedule"},
                "minute": {"type": "INTEGER", "description": "Minute to auto-activate (0-59)"}
            },
            "required": ["action"]
        }
    },
    {
        "name": "read_screen",
        "description": "Captura a tela e lê em voz alta o texto visível. Use quando o usuário pedir pra 'ler a tela', 'ler essa página', 'ler esse artigo'.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "proactive_check",
        "description": "Verifica proativamente se há algo pra informar o usuário: lembretes próximos, mudanças climáticas, notícias importantes. Chame esta tool a cada 5 minutos quando não houver interação do usuário.",
        "parameters": {
            "type": "OBJECT",
            "properties": {},
            "required": []
        }
    },
    {
        "name": "shopping_search",
        "description": "Busca produtos em lojas brasileiras (Mercado Livre, Magazine Luiza, Amazon) com filtros de frete grátis e promoção.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "query":        {"type": "STRING", "description": "Nome do produto a buscar"},
                "max_price":    {"type": "NUMBER", "description": "Preço máximo em R$"},
                "free_shipping":{"type": "BOOLEAN", "description": "Filtrar apenas frete grátis (padrão: true)"},
                "promotion":    {"type": "BOOLEAN", "description": "Filtrar apenas promoções/descontos (padrão: true)"},
                "store":        {"type": "STRING", "description": "mercadolivre | magazineluiza | amazon | all (padrão: all)"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "deep_research",
        "description": "Pesquisa profunda multi-rodadas na web. Decompõe a pergunta em sub-tópicos, busca fontes, extrai conteúdo, identifica lacunas e gera relatório completo. Suporta análise de PDFs/documentos, crawling de links internos, monitoramento automático de tópicos, e execução em background com progresso.",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "research (padrão) | compare | crawl | start_monitor | stop_monitor | status | monitor_status"
                },
                "query": {
                    "type": "STRING",
                    "description": "Pergunta ou tópico a pesquisar"
                },
                "depth": {
                    "type": "INTEGER",
                    "description": "Número de rodadas de aprofundamento (1-5). Padrão: 2"
                },
                "max_sources": {
                    "type": "INTEGER",
                    "description": "Máximo de fontes a consultar (1-30). Padrão: 10"
                },
                "save": {
                    "type": "BOOLEAN",
                    "description": "Salvar relatório em arquivo .md. Padrão: false"
                },
                "background": {
                    "type": "BOOLEAN",
                    "description": "Executar em background. Use get_research_status para acompanhar. Padrão: false"
                },
                "research_id": {
                    "type": "STRING",
                    "description": "ID da pesquisa para consultar status (usado com action=status)"
                },
                "file_paths": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Caminhos de PDFs/documentos para analisar como fontes"
                },
                "items": {
                    "type": "ARRAY",
                    "items": {"type": "STRING"},
                    "description": "Lista de itens para comparação (usado com action=compare)"
                },
                "aspect": {
                    "type": "STRING",
                    "description": "Aspecto para comparação: preço | specs | reviews | geral"
                },
                "crawl_depth": {
                    "type": "INTEGER",
                    "description": "Profundidade de crawling de links internos (1-3). Padrão: 1"
                },
                "topic": {
                    "type": "STRING",
                    "description": "Tópico para monitoramento automático (usado com action=start_monitor)"
                },
                "monitor_interval": {
                    "type": "INTEGER",
                    "description": "Intervalo em horas entre atualizações do monitor. Padrão: 6"
                },
                "monitor_id": {
                    "type": "STRING",
                    "description": "ID do monitor para parar (usado com action=stop_monitor)"
                },
                "format": {
                    "type": "STRING",
                    "description": "Formato do relatório: md | text. Padrão: md"
                }
            },
            "required": []
        }
    }
]
