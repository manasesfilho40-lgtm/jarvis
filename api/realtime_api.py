import asyncio
import json
import logging
import threading
import time
from typing import Any, Optional

logger = logging.getLogger("realtime_api")


HAS_FASTAPI = False
HAS_WEBSOCKETS = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    HAS_FASTAPI = True
except ImportError:
    pass
try:
    import uvicorn
    HAS_UVICORN = True
except ImportError:
    pass


class RealtimeAPI:
    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        self._host = host
        self._port = port
        self._app = None
        self._server = None
        self._connections: set[WebSocket] = set()
        self._running = False
        self._handlers: dict[str, callable] = {}
        self._loop = None
        self._thread: Optional[threading.Thread] = None

    def register_handler(self, action: str, handler: callable):
        self._handlers[action] = handler
        logger.debug(f"Handler registered for action: {action}")

    async def _handle_message(self, ws: WebSocket, data: dict):
        action = data.get("action", "")
        payload = data.get("payload", {})
        msg_id = data.get("id", str(time.time()))

        handler = self._handlers.get(action)
        if not handler:
            await self._send(ws, {"id": msg_id, "status": "error", "error": f"Unknown action: {action}"})
            return

        try:
            result = handler(payload)
            if hasattr(result, "__await__"):
                result = await result
            await self._send(ws, {"id": msg_id, "status": "ok", "result": result})
        except Exception as e:
            logger.error(f"Handler for '{action}' failed: {e}")
            await self._send(ws, {"id": msg_id, "status": "error", "error": str(e)})

    async def _send(self, ws: WebSocket, data: dict):
        try:
            await ws.send_json(data)
        except Exception as e:
            logger.warning(f"Send failed: {e}")

    async def broadcast(self, event: str, data: Any = None):
        message = json.dumps({"event": event, "data": data, "timestamp": time.time()})
        dead = set()
        for ws in self._connections:
            try:
                await ws.send_text(message)
            except Exception:
                dead.add(ws)
        self._connections -= dead

    async def _on_connect(self, ws: WebSocket):
        await ws.accept()
        self._connections.add(ws)
        logger.info(f"WebSocket client connected ({len(self._connections)} total)")

        try:
            while True:
                raw = await ws.receive_text()
                try:
                    data = json.loads(raw)
                    await self._handle_message(ws, data)
                except json.JSONDecodeError:
                    await self._send(ws, {"status": "error", "error": "Invalid JSON"})
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.warning(f"WebSocket error: {e}")
        finally:
            self._connections.discard(ws)
            logger.info(f"WebSocket client disconnected ({len(self._connections)} remaining)")

    def _build_app(self) -> Optional["FastAPI"]:
        if not HAS_FASTAPI:
            logger.warning("FastAPI not available")
            return None

        app = FastAPI(title="J.A.R.V.I.S Realtime API", version="3.0.0")

        @app.get("/")
        async def root():
            return {
                "service": "J.A.R.V.I.S Realtime API",
                "version": "3.0.0",
                "connections": len(self._connections),
                "handlers": list(self._handlers.keys()),
                "status": "running" if self._running else "stopped",
            }

        @app.get("/health")
        async def health():
            return {
                "status": "healthy",
                "connections": len(self._connections),
                "uptime": time.time() - self._start_time if hasattr(self, "_start_time") else 0,
            }

        @app.get("/stats")
        async def stats():
            return {
                "connections": len(self._connections),
                "handlers": len(self._handlers),
                "actions": list(self._handlers.keys()),
            }

        @app.websocket("/ws")
        async def websocket_endpoint(ws: WebSocket):
            await self._on_connect(ws)

        return app

    async def start(self):
        if self._running:
            logger.warning("RealtimeAPI already running")
            return

        if not HAS_FASTAPI:
            logger.error("Cannot start RealtimeAPI: FastAPI not installed")
            return

        self._app = self._build_app()
        if not self._app:
            return

        self._loop = asyncio.get_event_loop()
        self._running = True
        self._start_time = time.time()

        config = uvicorn.Config(
            self._app,
            host=self._host,
            port=self._port,
            log_level="warning",
            ws_max_size=1048576,
        )
        self._server = uvicorn.Server(config)
        logger.info(f"RealtimeAPI starting on ws://{self._host}:{self._port}/ws")
        await self._server.serve()

    def start_in_thread(self):
        def _run():
            asyncio.run(self.start())

        self._thread = threading.Thread(target=_run, daemon=True, name="realtime-api")
        self._thread.start()
        logger.info(f"RealtimeAPI thread started on ws://{self._host}:{self._port}/ws")

    async def stop(self):
        self._running = False
        for ws in set(self._connections):
            try:
                await ws.close()
            except Exception:
                pass
        self._connections.clear()

        if self._server:
            self._server.should_exit = True
            logger.info("RealtimeAPI server stopping")

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def connection_count(self) -> int:
        return len(self._connections)


_realtime_api_instance = None


def get_realtime_api(host: str = "127.0.0.1", port: int = 8765) -> RealtimeAPI:
    global _realtime_api_instance
    if _realtime_api_instance is None:
        _realtime_api_instance = RealtimeAPI(host=host, port=port)
    return _realtime_api_instance
