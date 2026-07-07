"""Google Home Bridge add-on entrypoint."""

from __future__ import annotations

import asyncio
import logging
import os
import ssl
import sys

from aiohttp import web

import installer
from options import INGRESS_PORT, PROXY_PORT, UPSTREAM, Options
from proxy import create_proxy_app
from wizard import create_wizard_app

_LOGGER = logging.getLogger("bridge")


async def run_cloudflared(options: Options, runtime: dict) -> None:
    """Run the Cloudflare Tunnel connector, restarting with backoff."""
    backoff = 5
    while True:
        _LOGGER.info("Starting cloudflared tunnel")
        process = await asyncio.create_subprocess_exec(
            "cloudflared",
            "tunnel",
            "--no-autoupdate",
            "run",
            "--token",
            options.cloudflared_token,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        runtime["cloudflared_running"] = True
        assert process.stdout
        async for line in process.stdout:
            _LOGGER.info("[cloudflared] %s", line.decode().rstrip())
        await process.wait()
        runtime["cloudflared_running"] = False
        _LOGGER.warning(
            "cloudflared exited with %s, restarting in %ss",
            process.returncode,
            backoff,
        )
        await asyncio.sleep(backoff)
        backoff = min(backoff * 2, 300)


async def main() -> None:
    """Run the bridge."""
    options = Options.load()
    logging.basicConfig(
        level=getattr(logging, options.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
    _LOGGER.info("Mode: %s, upstream: %s", options.mode, UPSTREAM)

    runtime: dict = {"restart_required": False, "cloudflared_running": False}

    if options.install_integration:
        changed = installer.install_integration()
        if changed:
            runtime["restart_required"] = True
            _LOGGER.warning(
                "Cloud shim integration installed/updated — restart Home "
                "Assistant to activate it (the wizard has a button for this)"
            )

    wizard_runner = web.AppRunner(create_wizard_app(options, runtime))
    await wizard_runner.setup()
    await web.TCPSite(wizard_runner, "0.0.0.0", INGRESS_PORT).start()
    _LOGGER.info("Ingress wizard listening on %s", INGRESS_PORT)

    proxy_runner = web.AppRunner(
        create_proxy_app(UPSTREAM), access_log=logging.getLogger("bridge.access")
    )
    await proxy_runner.setup()

    ssl_context = None
    host = "0.0.0.0"
    if options.mode == "direct":
        certfile = f"/ssl/{options.certfile}"
        keyfile = f"/ssl/{options.keyfile}"
        if not (os.path.isfile(certfile) and os.path.isfile(keyfile)):
            _LOGGER.error(
                "Direct mode needs %s and %s — configure the SSL add-on or "
                "switch modes",
                certfile,
                keyfile,
            )
            sys.exit(1)
        ssl_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ssl_context.load_cert_chain(certfile, keyfile)
    elif options.mode == "cloudflared":
        host = "127.0.0.1"

    await web.TCPSite(proxy_runner, host, PROXY_PORT, ssl_context=ssl_context).start()
    _LOGGER.info(
        "Public proxy listening on %s:%s (%s)",
        host,
        PROXY_PORT,
        "TLS" if ssl_context else "plain HTTP",
    )

    if options.mode == "cloudflared":
        if not options.cloudflared_token:
            _LOGGER.error(
                "Mode is cloudflared but no cloudflared_token is configured. "
                "The wizard explains how to create a tunnel"
            )
        else:
            asyncio.create_task(run_cloudflared(options, runtime))

    await asyncio.Event().wait()


if __name__ == "__main__":
    asyncio.run(main())
