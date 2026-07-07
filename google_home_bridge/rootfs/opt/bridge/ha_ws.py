"""Minimal Home Assistant websocket client via the Supervisor proxy."""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

from options import SUPERVISOR_TOKEN, SUPERVISOR_WS

_LOGGER = logging.getLogger(__name__)


class HAWebsocketError(Exception):
    """Raised when a websocket command fails."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message


async def ws_command(command: dict[str, Any]) -> Any:
    """Run a single websocket command against HA core and return its result."""
    try:
        return await _ws_command(command)
    except (aiohttp.ClientError, TimeoutError, OSError) as err:
        raise HAWebsocketError("connection", f"cannot reach Home Assistant: {err}") from err


async def _ws_command(command: dict[str, Any]) -> Any:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.ws_connect(SUPERVISOR_WS) as ws:
            msg = await ws.receive_json()
            if msg.get("type") != "auth_required":
                raise HAWebsocketError("protocol", f"unexpected greeting: {msg}")
            await ws.send_json(
                {"type": "auth", "access_token": SUPERVISOR_TOKEN}
            )
            msg = await ws.receive_json()
            if msg.get("type") != "auth_ok":
                raise HAWebsocketError("auth", f"authentication failed: {msg}")

            await ws.send_json({"id": 1, **command})
            while True:
                msg = await ws.receive_json()
                if msg.get("id") != 1 or msg.get("type") != "result":
                    continue
                if not msg.get("success"):
                    error = msg.get("error") or {}
                    raise HAWebsocketError(
                        error.get("code", "unknown"),
                        error.get("message", "unknown error"),
                    )
                return msg.get("result")
