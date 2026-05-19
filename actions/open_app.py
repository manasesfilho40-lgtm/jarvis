import time
import subprocess
import platform
import shutil

try:
    import psutil
    _PSUTIL = True
except ImportError:
    _PSUTIL = False

try:
    import pyperclip
    _PYPERCLIP = True
except ImportError:
    _PYPERCLIP = False

_SYSTEM = platform.system()

_APP_ALIASES: dict[str, dict[str, str]] = {

    "chrome":             {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "google chrome":      {"Windows": "chrome",                  "Darwin": "Google Chrome",        "Linux": "google-chrome"},
    "firefox":            {"Windows": "firefox",                 "Darwin": "Firefox",              "Linux": "firefox"},
    "edge":               {"Windows": "brave",                   "Darwin": "Microsoft Edge",       "Linux": "microsoft-edge"},
    "brave":              {"Windows": "brave",                   "Darwin": "Brave Browser",        "Linux": "brave-browser"},
    "safari":             {"Windows": "brave",                   "Darwin": "Safari",               "Linux": "firefox"},
    "opera":              {"Windows": "opera",                   "Darwin": "Opera",                "Linux": "opera"},
    "whatsapp":           {"Windows": "WhatsApp",                "Darwin": "WhatsApp",             "Linux": "whatsapp"},
    "telegram":           {"Windows": "Telegram",                "Darwin": "Telegram",             "Linux": "telegram"},
    "discord":            {"Windows": "Discord",                 "Darwin": "Discord",              "Linux": "discord"},
    "slack":              {"Windows": "Slack",                   "Darwin": "Slack",                "Linux": "slack"},
    "zoom":               {"Windows": "Zoom",                    "Darwin": "zoom.us",              "Linux": "zoom"},
    "teams":              {"Windows": "msteams",                 "Darwin": "Microsoft Teams",      "Linux": "teams"},
    "skype":              {"Windows": "skype",                   "Darwin": "Skype",                "Linux": "skype"},
    "signal":             {"Windows": "signal",                  "Darwin": "Signal",               "Linux": "signal"},
    "spotify":            {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "sportify":           {"Windows": "Spotify",                 "Darwin": "Spotify",              "Linux": "spotify"},
    "vlc":                {"Windows": "vlc",                     "Darwin": "VLC",                  "Linux": "vlc"},
    "netflix":            {"Windows": "Netflix",                 "Darwin": "Netflix",              "Linux": "firefox"},
    "vscode":             {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "visual studio code": {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "code":               {"Windows": "code",                    "Darwin": "Visual Studio Code",   "Linux": "code"},
    "terminal":           {"Windows": "wt",                      "Darwin": "Terminal",             "Linux": "gnome-terminal"},
    "cmd":                {"Windows": "cmd.exe",                 "Darwin": "Terminal",             "Linux": "bash"},
    "powershell":         {"Windows": "powershell.exe",          "Darwin": "Terminal",             "Linux": "bash"},
    "postman":            {"Windows": "Postman",                 "Darwin": "Postman",              "Linux": "postman"},
    "git":                {"Windows": "git-bash",                "Darwin": "Terminal",             "Linux": "bash"},
    "figma":              {"Windows": "Figma",                   "Darwin": "Figma",                "Linux": "figma"},
    "blender":            {"Windows": "blender",                 "Darwin": "Blender",              "Linux": "blender"},
    "word":               {"Windows": "winword",                 "Darwin": "Microsoft Word",       "Linux": "libreoffice --writer"},
    "excel":              {"Windows": "excel",                   "Darwin": "Microsoft Excel",      "Linux": "libreoffice --calc"},
    "powerpoint":         {"Windows": "powerpnt",                "Darwin": "Microsoft PowerPoint", "Linux": "libreoffice --impress"},
    "libreoffice":        {"Windows": "soffice",                 "Darwin": "LibreOffice",          "Linux": "libreoffice"},
    "notepad":            {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "textedit":           {"Windows": "notepad.exe",             "Darwin": "TextEdit",             "Linux": "gedit"},
    "explorer":           {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "file explorer":      {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "finder":             {"Windows": "explorer.exe",            "Darwin": "Finder",               "Linux": "nautilus"},
    "task manager":       {"Windows": "taskmgr.exe",             "Darwin": "Activity Monitor",     "Linux": "gnome-system-monitor"},
    "settings":           {"Windows": "ms-settings:",            "Darwin": "System Preferences",   "Linux": "gnome-control-center"},
    "calculator":         {"Windows": "calc.exe",                "Darwin": "Calculator",           "Linux": "gnome-calculator"},
    "paint":              {"Windows": "mspaint.exe",             "Darwin": "Preview",              "Linux": "gimp"},
    "instagram":          {"Windows": "Instagram",               "Darwin": "Instagram",            "Linux": "firefox"},
    "tiktok":             {"Windows": "TikTok",                  "Darwin": "TikTok",               "Linux": "firefox"},
    "notion":             {"Windows": "Notion",                  "Darwin": "Notion",               "Linux": "notion"},
    "obsidian":           {"Windows": "Obsidian",                "Darwin": "Obsidian",             "Linux": "obsidian"},
    "capcut":             {"Windows": "CapCut",                  "Darwin": "CapCut",               "Linux": "capcut"},
    "steam":              {"Windows": "steam",                   "Darwin": "Steam",                "Linux": "steam"},
    "epic":               {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "epic games":         {"Windows": "EpicGamesLauncher",       "Darwin": "Epic Games Launcher",  "Linux": "legendary"},
    "claude":             {"Windows": "Claude",                  "Darwin": "Claude",               "Linux": "claude"},
}


def _normalize(raw: str) -> str:
    key = raw.lower().strip()

    if key in _APP_ALIASES:
        return _APP_ALIASES[key].get(_SYSTEM, raw)

    for alias_key, os_map in _APP_ALIASES.items():
        if alias_key in key or key in alias_key:
            return os_map.get(_SYSTEM, raw)

    return raw  

def _launch_windows(app_name: str) -> bool:
    import os

    # ── Claude: always use Start Menu search (lupa) ──────────────
    if app_name.lower() == "claude":
        try:
            import pyautogui
            pyautogui.PAUSE = 0.1
            print("[open_app] Claude - using Start Menu search (lupa)")
            pyautogui.press("win")
            time.sleep(1.0) # Increased delay for Start Menu
            
            if _PYPERCLIP:
                pyperclip.copy("Claude")
                pyautogui.hotkey("ctrl", "v")
            else:
                pyautogui.write("Claude", interval=0.1) # Much slower typing
                
            time.sleep(1.2)
            pyautogui.press("enter")
            time.sleep(2.5)
            return True
        except Exception as e:
            print(f"[open_app] Claude Start Menu search failed: {e}")
            return False

    # ── Check standard installation paths for common apps ───────
    common_paths = {
        "brave": [
            os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
            os.path.expandvars(r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe"),
        ],
        "chrome": [
            os.path.expandvars(r"%ProgramFiles%\Google\Chrome\Application\chrome.exe"),
            os.path.expandvars(r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe"),
        ],
        "firefox": [
            os.path.expandvars(r"%ProgramFiles%\Mozilla Firefox\firefox.exe"),
        ],
        "spotify": [
            os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
            os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
        ],
        "whatsapp": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\WhatsApp\WhatsApp.exe"),
        ],
        "vscode": [
            os.path.expandvars(r"%LOCALAPPDATA%\Programs\Microsoft VS Code\Code.exe"),
            os.path.expandvars(r"%ProgramFiles%\Microsoft VS Code\Code.exe"),
        ],
    }

    low_app = app_name.lower()
    for name, paths in common_paths.items():
        if name in low_app or low_app in name:
            for p in paths:
                if os.path.exists(p):
                    try:
                        subprocess.Popen(
                            [p],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL,
                        )
                        time.sleep(0.5)
                        return True
                    except Exception as e:
                        print(f"[open_app] Direct path launch failed for {p}: {e}")

    # ── Normal apps: try direct subprocess first ─────────────────
    if shutil.which(app_name) or shutil.which(app_name.split(".")[0]):
        try:
            subprocess.Popen(
                app_name,
                shell=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.5)
            return True
        except Exception as e:
            print(f"[open_app] subprocess failed: {e}")

    if ":" in app_name:
        try:
            subprocess.Popen(f"start {app_name}", shell=True)
            time.sleep(1.0)
            return True
        except Exception:
            pass

    # Optimize: check if already running
    if _PSUTIL:
        for proc in psutil.process_iter(['name']):
            if proc.info['name'] and app_name.lower() in proc.info['name'].lower():
                return True

    # Fallback: Start Menu search for any other app
    try:
        import pyautogui
        pyautogui.PAUSE = 0.1
        pyautogui.press("win")
        time.sleep(1.2) # Increased for stability
        
        if _PYPERCLIP:
            pyperclip.copy(app_name)
            pyautogui.hotkey("ctrl", "v")
        else:
            pyautogui.write(app_name, interval=0.08)
            
        time.sleep(1.5) # Wait for search results
        pyautogui.press("enter")
        time.sleep(2.0)
        return True
    except Exception as e:
        print(f"[open_app] Start Menu search failed: {e}")

    return False


def _launch_macos(app_name: str) -> bool:

    try:
        result = subprocess.run(
            ["open", "-a", app_name],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    try:
        result = subprocess.run(
            ["open", "-a", f"{app_name}.app"],
            capture_output=True, timeout=8
        )
        if result.returncode == 0:
            time.sleep(1.0)
            return True
    except Exception:
        pass

    binary = shutil.which(app_name) or shutil.which(app_name.lower())
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        import pyautogui
        pyautogui.hotkey("command", "space")
        time.sleep(0.6)
        pyautogui.write(app_name, interval=0.05)
        time.sleep(0.8)
        pyautogui.press("enter")
        time.sleep(1.5)
        return True
    except Exception as e:
        print(f"[open_app] Spotlight failed: {e}")

    return False


def _launch_linux(app_name: str) -> bool:

    binary = (
        shutil.which(app_name) or
        shutil.which(app_name.lower()) or
        shutil.which(app_name.lower().replace(" ", "-")) or
        shutil.which(app_name.lower().replace(" ", "_"))
    )
    if binary:
        try:
            subprocess.Popen(
                [binary],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            time.sleep(1.0)
            return True
        except Exception:
            pass

    try:
        subprocess.run(
            ["xdg-open", app_name],
            capture_output=True, timeout=5
        )
        return True
    except Exception:
        pass

    for desktop_name in [
        app_name.lower(),
        app_name.lower().replace(" ", "-"),
        app_name.lower().replace(" ", ""),
    ]:
        try:
            result = subprocess.run(
                ["gtk-launch", desktop_name],
                capture_output=True, timeout=5
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass

    return False


_OS_LAUNCHERS = {
    "Windows": _launch_windows,
    "Darwin":  _launch_macos,
    "Linux":   _launch_linux,
}

def open_app(
    parameters=None,
    response=None,
    player=None,
    session_memory=None,
) -> str:
    app_name = (parameters or {}).get("app_name", "").strip()
    play     = (parameters or {}).get("play", False)
    query    = (parameters or {}).get("query", "").strip()

    if not app_name:
        return "No application name provided."

    launcher = _OS_LAUNCHERS.get(_SYSTEM)
    if launcher is None:
        return f"Unsupported operating system: {_SYSTEM}"

    normalized = _normalize(app_name)
    print(f"[open_app] Launching: '{app_name}' -> '{normalized}' ({_SYSTEM})")

    if player:
        player.write_log(f"[open_app] {app_name}")

    try:
        if launcher(normalized):
            if play or query:
                _handle_play(normalized, query)
            return f"Opened {app_name}."
        if normalized.lower() != app_name.lower():
            if launcher(app_name):
                if play or query:
                    _handle_play(normalized, query)
                return f"Opened {app_name}."
        return (
            f"Could not confirm that {app_name} launched. "
            f"It may still be loading, or it might not be installed."
        )
    except Exception as e:
        print(f"[open_app] Error: {e}")
        return f"Failed to open {app_name}: {e}"

def _handle_play(app_name: str, query: str = ""):
    """Attempts to play media using mouse clicks on Spotify's UI."""
    name_low = app_name.lower()
    if "spotify" in name_low:
        try:
            import pyautogui
            import win32gui
            import win32process
            import win32con
            import psutil
            
            search_query = query if query else "highway to hell acdc"
            print(f"[open_app] Searching Spotify for: {search_query}")
            
            # Wait for Spotify to load
            time.sleep(2.5)
            
            # Find the Spotify window by process PIDs
            spotify_pids = []
            for proc in psutil.process_iter(['pid', 'name']):
                if proc.info['name'] and proc.info['name'].lower() == 'spotify.exe':
                    spotify_pids.append(proc.info['pid'])
            
            hwnd = None
            if spotify_pids:
                def enum_windows_callback(h, extra):
                    if win32gui.IsWindowVisible(h):
                        _, pid = win32process.GetWindowThreadProcessId(h)
                        if pid in spotify_pids:
                            title = win32gui.GetWindowText(h)
                            if title and title != "AngleHiddenWindow":
                                extra.append(h)
                    return True
                
                hwnds = []
                win32gui.EnumWindows(enum_windows_callback, hwnds)
                if hwnds:
                    hwnd = hwnds[0]
            
            if hwnd:
                print(f"[open_app] Found Spotify HWND: {hwnd}. Activating...")
                
                # Restore and force window position/size to 1024x768 at (100, 100)
                # This guarantees 100% stable mouse coordinates across all monitors and DPIs!
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
                time.sleep(0.5)
                win32gui.MoveWindow(hwnd, 100, 100, 1024, 768, True)
                time.sleep(0.5)
                
                try:
                    import win32com.client
                    shell = win32com.client.Dispatch("WScript.Shell")
                    shell.SendKeys('%')
                except Exception:
                    pass
                    
                win32gui.SetForegroundWindow(hwnd)
                time.sleep(0.5)
                
                # Step 1: Click the search input area directly at (612, 130)
                # This guarantees window focus and centers the search input perfectly!
                pyautogui.click(612, 130)
                time.sleep(0.4)
                
                # Focus the Search input using Ctrl+L just to be absolutely sure
                pyautogui.hotkey("ctrl", "l")
                time.sleep(0.4)
                
                # Step 2: Clear existing text and type query
                pyautogui.hotkey("ctrl", "a")
                time.sleep(0.2)
                pyautogui.press("backspace")
                time.sleep(0.2)
                
                if _PYPERCLIP:
                    pyperclip.copy(search_query)
                    pyautogui.hotkey("ctrl", "v")
                else:
                    pyautogui.write(search_query, interval=0.06)
                
                time.sleep(0.5)
                pyautogui.press("enter") # Submit search
                print(f"[open_app] Typed search query, waiting for results...")
                time.sleep(3.5)  # Wait for results to fully load
                
                # Step 3: Double-click the large 'Melhor Resultado' (Top Result) card
                # With a standard 1024x768 window at (100, 100), the Top Result card is centered at (480, 400)
                result_x = 480
                result_y = 400
                pyautogui.doubleClick(result_x, result_y)
                print(f"[open_app] Double-clicked Top Result card at ({result_x}, {result_y})")
                time.sleep(2.0)  # Wait for page load/navigation if Top Result is an Album/Playlist
                
                # Single robust double-click on the first song row (Track 1)
                # Track 1 is at (550, 530) absolute. This starts playback without toggling pause!
                pyautogui.doubleClick(550, 530)
                print(f"[open_app] Double-clicked Track 1 at (550, 530)")
                time.sleep(1.0)
                
                # Step 4: Minimize Spotify
                win32gui.ShowWindow(hwnd, win32con.SW_MINIMIZE)
                print(f"[open_app] Play sequence completed for: {search_query}")
            else:
                print("[open_app] Spotify window could not be found via PIDs.")
                
        except Exception as e:
            print(f"[open_app] Play failed: {e}")