"""WebSocket push: a Postgres LISTEN/NOTIFY watcher fans DB changes out to
connected dashboard clients instantly.

A DB trigger runs ``pg_notify('govintel_changed', <table>)`` on any change to
``opportunities`` / ``lead_scores`` (see ``scripts/notify_triggers.sql``). The
``db_listener`` task LISTENs on a dedicated async connection and broadcasts a
content-free ``{"type": "leads_changed"}`` signal; clients re-fetch through the
authenticated HTTP API, so no lead data travels over the socket.
"""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, status
from starlette.websockets import WebSocketState

logger = logging.getLogger("govintel.api")
router = APIRouter()


class ConnectionManager:
    def __init__(self) -> None:
        self.active: set[WebSocket] = set()

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.active.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self.active.discard(ws)

    async def broadcast(self, message: dict) -> None:
        for ws in list(self.active):
            try:
                if ws.application_state == WebSocketState.CONNECTED:
                    await ws.send_json(message)
            except Exception:
                self.disconnect(ws)


def _libpq_dsn(database_url: str) -> str:
    # SQLAlchemy DSN "postgresql+psycopg://..." -> libpq "postgresql://..."
    return database_url.replace("+psycopg", "", 1)


def _listen_blocking(dsn: str, manager: "ConnectionManager", loop: asyncio.AbstractEventLoop,
                     stop: "threading.Event") -> None:
    """Run in a dedicated thread: a *synchronous* psycopg connection LISTENs and
    hands each notification back to the app's event loop. A sync connection avoids
    psycopg's incompatibility with Windows' ProactorEventLoop under async mode."""
    import psycopg

    while not stop.is_set():
        try:
            with psycopg.connect(dsn, autocommit=True) as conn:
                conn.execute("LISTEN govintel_changed")
                logger.info('{"event": "ws_listener_ready"}')
                while not stop.is_set():
                    # Yield control every second so `stop` is honoured promptly.
                    for note in conn.notifies(timeout=1.0):
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast({"type": "leads_changed", "source": note.payload}),
                            loop,
                        )
        except Exception as exc:  # noqa: BLE001 - keep the listener alive
            if stop.is_set():
                return
            logger.warning('{"event": "ws_listener_error", "detail": "%s"}', exc)
            stop.wait(2)


async def db_listener(app) -> None:
    """Start the LISTEN watcher thread and keep it alive until cancelled. Only
    started when a real database is configured."""
    import threading

    loop = asyncio.get_running_loop()
    stop = threading.Event()
    dsn = _libpq_dsn(app.state.settings.database_url)
    thread = threading.Thread(
        target=_listen_blocking, args=(dsn, app.state.ws_manager, loop, stop),
        name="ws-db-listener", daemon=True,
    )
    thread.start()
    try:
        while True:
            await asyncio.sleep(3600)
    except asyncio.CancelledError:
        stop.set()
        raise


@router.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    settings = ws.app.state.settings
    token = ws.query_params.get("token")
    # The socket only carries content-free change signals, but still gate it on a
    # valid API key when keys are configured.
    if settings.api_keys and token not in settings.api_keys:
        await ws.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    manager: ConnectionManager = ws.app.state.ws_manager
    await manager.connect(ws)
    try:
        await ws.send_json({"type": "connected"})
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30)
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})  # keepalive
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        manager.disconnect(ws)
