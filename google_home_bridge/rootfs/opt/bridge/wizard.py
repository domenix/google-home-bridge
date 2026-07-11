"""Ingress setup wizard API."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any

import aiohttp
from aiohttp import web

import installer
from ha_ws import HAWebsocketError, ws_command
from options import SUPERVISOR_API, SUPERVISOR_TOKEN, Options

_LOGGER = logging.getLogger(__name__)

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


def _json_error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _bridge_ws(command: dict[str, Any]) -> Any:
    try:
        return await ws_command(command)
    except HAWebsocketError as err:
        raise web.HTTPBadGateway(
            text=json.dumps({"error": str(err)}), content_type="application/json"
        ) from err


def create_wizard_app(options: Options, runtime: dict[str, Any]) -> web.Application:
    """Create the ingress wizard application."""

    async def get_status(request: web.Request) -> web.Response:
        """Aggregate status for the wizard UI."""
        status: dict[str, Any] = {
            "mode": options.mode,
            "public_url": options.public_url,
            "cloudflared_running": runtime.get("cloudflared_running", False),
            "cloudflared_token_set": bool(options.cloudflared_token),
            "integration_installed": installer.integration_installed(),
            "integration_up_to_date": installer.integration_up_to_date(),
            "restart_required": runtime.get("restart_required", False),
            "shim_active": False,
            "bridge": None,
        }
        try:
            cloud_status = await ws_command({"type": "cloud/status"})
            status["shim_active"] = bool(cloud_status.get("bridge"))
        except HAWebsocketError as err:
            status["shim_error"] = str(err)

        if status["shim_active"]:
            try:
                status["bridge"] = await ws_command({"type": "cloud/bridge/config"})
            except HAWebsocketError as err:
                status["bridge_error"] = str(err)

        return web.json_response(status)

    async def post_config(request: web.Request) -> web.Response:
        """Store project id / service account / public URL in the shim."""
        body = await request.json()
        command: dict[str, Any] = {"type": "cloud/bridge/update_config"}

        if "project_id" in body:
            command["project_id"] = body["project_id"] or None
        if "public_url" in body:
            command["public_url"] = (body["public_url"] or "").rstrip("/") or None
        if body.get("service_account"):
            service_account = body["service_account"]
            if isinstance(service_account, str):
                try:
                    service_account = json.loads(service_account)
                except json.JSONDecodeError:
                    return _json_error("Service account is not valid JSON")
            if not isinstance(service_account, dict) or not {
                "client_email",
                "private_key",
            } <= service_account.keys():
                return _json_error(
                    "Service account JSON must contain client_email and private_key"
                )
            command["service_account"] = {
                "client_email": service_account["client_email"],
                "private_key": service_account["private_key"],
            }

        result = await _bridge_ws(command)
        return web.json_response({"ok": True, **(result or {})})

    async def post_sync(request: web.Request) -> web.Response:
        """Trigger a Google requestSync."""
        await _bridge_ws({"type": "cloud/bridge/sync"})
        return web.json_response({"ok": True})

    async def post_test_public(request: web.Request) -> web.Response:
        """Verify the public URL reaches this Home Assistant instance."""
        body = await request.json()
        public_url = (body.get("public_url") or options.public_url or "").rstrip("/")
        if not public_url.startswith("https://"):
            return _json_error("Public URL must start with https://")

        checks = {}
        timeout = aiohttp.ClientTimeout(total=15)
        try:
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{public_url}/auth/providers") as res:
                    checks["auth_providers"] = res.status
                async with session.post(
                    f"{public_url}/api/google_assistant", json={}
                ) as res:
                    checks["fulfillment"] = res.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            return _json_error(f"Could not reach {public_url}: {err}", status=502)

        ok = checks.get("auth_providers") == 200 and checks.get("fulfillment") == 401
        return web.json_response({"ok": ok, "checks": checks})

    async def post_install(request: web.Request) -> web.Response:
        """Install/update the bundled integration."""
        changed = await asyncio.get_running_loop().run_in_executor(
            None, installer.install_integration
        )
        if changed:
            runtime["restart_required"] = True
        return web.json_response(
            {"ok": True, "changed": changed, "restart_required": changed}
        )

    async def post_restart_core(request: web.Request) -> web.Response:
        """Restart Home Assistant core via the Supervisor."""
        timeout = aiohttp.ClientTimeout(total=30)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"{SUPERVISOR_API}/core/restart",
                headers={"Authorization": f"Bearer {SUPERVISOR_TOKEN}"},
            ) as res:
                if res.status != 200:
                    return _json_error(
                        f"Supervisor returned {res.status}", status=502
                    )
        runtime["restart_required"] = False
        return web.json_response({"ok": True})

    async def index(request: web.Request) -> web.FileResponse:
        return web.FileResponse(os.path.join(STATIC_DIR, "index.html"))

    app = web.Application()
    app.router.add_get("/", index)
    app.router.add_get("/api/status", get_status)
    app.router.add_post("/api/config", post_config)
    app.router.add_post("/api/sync", post_sync)
    app.router.add_post("/api/test_public", post_test_public)
    app.router.add_post("/api/install", post_install)
    app.router.add_post("/api/restart_core", post_restart_core)
    return app
