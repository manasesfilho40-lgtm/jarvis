import asyncio
import json
import threading
from pathlib import Path
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn

BASE_DIR = Path(__file__).resolve().parent
app = FastAPI(title="JARVIS Mobile Bridge")

command_queue = asyncio.Queue()
ws_clients = set()

FALLBACK_HTML = "<html><body><h1>JARVIS Mobile Bridge</h1><p>UI file not found. Run with desktop UI for full interface.</p></body></html>"

@app.get("/")
async def index():
    try:
        html = (BASE_DIR / "jarvis_ui.html").read_text(encoding="utf-8")
    except FileNotFoundError:
        return HTMLResponse(FALLBACK_HTML)
    html = html.replace(
        "</head>",
        """<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
<script>
let ws = new WebSocket((location.protocol==='https'?'wss://':'ws://')+location.host+'/ws');
ws.onmessage = function(e) {
  try { const d = JSON.parse(e.data);
    if (d.type==='log') addLog(d.is_user, d.msg);
    if (d.type==='state') updateState(d.state);
  } catch(ex) {}
};
function sendCommand(text) {
  fetch('/command', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({text:text})});
}
window.addEventListener('load', function() {
  document.addEventListener('click', function(e) {
    var btn = e.target.closest('[data-cmd]');
    if (btn) sendCommand(btn.getAttribute('data-cmd'));
  });
  var orig = document.getElementById('speak-btn-text');
  if (orig) orig.textContent = 'Toque para comando';
});
</script>
</head>""",
    )
    return HTMLResponse(html)

@app.post("/command")
async def receive_command(req: Request):
    body = await req.json()
    text = body.get("text", "")
    if text:
        from core.utils import global_command_queue
        global_command_queue.append(text)
        return JSONResponse({"ok": True})
    return JSONResponse({"ok": False}, status_code=400)

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    ws_clients.add(ws)
    try:
        while True:
            data = await ws.receive_text()
            try:
                msg = json.loads(data)
                text = msg.get("text", "") or msg.get("command", "") or data
            except json.JSONDecodeError:
                text = data
            if text:
                from core.utils import global_command_queue
                global_command_queue.append(text)
    except Exception:
        pass
    finally:
        ws_clients.discard(ws)

async def broadcast(msg: dict):
    for ws in list(ws_clients):
        try:
            await ws.send_json(msg)
        except Exception:
            ws_clients.discard(ws)

def start_server(port: int = 5050):
    config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level="warning")
    server = uvicorn.Server(config)
    server.run()

def _push_log(is_user: bool, msg: str):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(broadcast({"type": "log", "is_user": is_user, "msg": msg}))
    except Exception:
        pass

def _push_state(state: str):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(broadcast({"type": "state", "state": state}))
    except Exception:
        pass

def _push_model_info(info_json: str):
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            loop.create_task(broadcast({"type": "model_info", "data": info_json}))
    except Exception:
        pass
