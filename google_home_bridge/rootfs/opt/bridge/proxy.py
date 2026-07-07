"""Selective reverse proxy exposing only what Google needs.

Google account linking and fulfillment require exactly these surfaces of
Home Assistant to be publicly reachable:

- POST /api/google_assistant   (fulfillment, HA bearer-token auth)
- /auth/authorize + assets     (the HA login page for account linking)
- POST /auth/token             (OAuth token exchange by Google's servers)

Everything else is rejected, so the public hostname exposes a far smaller
attack surface than port-forwarding all of Home Assistant.
"""

from __future__ import annotations

import logging

from aiohttp import ClientSession, ClientTimeout, web

_LOGGER = logging.getLogger(__name__)

ALLOWED_EXACT = {
    "/api/google_assistant",
    "/api/onboarding",
    "/manifest.json",
}
ALLOWED_PREFIXES = (
    "/auth/",
    "/frontend_latest/",
    "/frontend_es5/",
    "/static/",
)

HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def _allowed(path: str) -> bool:
    return path in ALLOWED_EXACT or path.startswith(ALLOWED_PREFIXES)


def create_proxy_app(upstream: str) -> web.Application:
    """Create the public-facing proxy application."""
    session = ClientSession(timeout=ClientTimeout(total=60))

    async def close_session(app: web.Application) -> None:
        await session.close()

    async def handle(request: web.Request) -> web.StreamResponse:
        if not _allowed(request.path):
            _LOGGER.debug("Blocked %s %s", request.method, request.path)
            return web.Response(status=403, text="Forbidden")

        url = f"{upstream}{request.path_qs}"
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in HOP_BY_HOP and key.lower() != "host"
        }
        peer = request.remote or ""
        forwarded_for = request.headers.get("X-Forwarded-For")
        headers["X-Forwarded-For"] = (
            f"{forwarded_for}, {peer}" if forwarded_for else peer
        )
        headers["X-Forwarded-Proto"] = "https"

        try:
            async with session.request(
                request.method,
                url,
                headers=headers,
                data=request.content if request.body_exists else None,
                allow_redirects=False,
            ) as upstream_response:
                response = web.StreamResponse(
                    status=upstream_response.status,
                    headers={
                        key: value
                        for key, value in upstream_response.headers.items()
                        if key.lower() not in HOP_BY_HOP
                        and key.lower() != "content-length"
                    },
                )
                await response.prepare(request)
                async for chunk in upstream_response.content.iter_chunked(65536):
                    await response.write(chunk)
                await response.write_eof()
                return response
        except OSError as err:
            _LOGGER.error("Upstream request to %s failed: %s", url, err)
            return web.Response(status=502, text="Bad Gateway")

    app = web.Application()
    app.on_cleanup.append(close_session)
    app.router.add_route("*", "/{tail:.*}", handle)
    return app
