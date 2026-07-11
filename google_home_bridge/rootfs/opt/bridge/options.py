"""Add-on options and environment."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

OPTIONS_FILE = "/data/options.json"

UPSTREAM = os.environ.get("BRIDGE_UPSTREAM", "http://homeassistant.local.hass.io:8123")
SUPERVISOR_TOKEN = os.environ.get("SUPERVISOR_TOKEN", "")
SUPERVISOR_WS = "ws://supervisor/core/websocket"
SUPERVISOR_API = "http://supervisor"

PROXY_PORT = 8124
INGRESS_PORT = 8099

COMPONENT_SRC = "/opt/bridge/custom_components/cloud"
COMPONENT_DST = "/homeassistant/custom_components/cloud"


@dataclass
class Options:
    """Parsed add-on options."""

    mode: str
    public_url: str
    certfile: str
    keyfile: str
    install_integration: bool
    log_level: str

    @classmethod
    def load(cls) -> "Options":
        """Load options from the supervisor-provided options file."""
        try:
            with open(OPTIONS_FILE, encoding="utf-8") as fp:
                raw = json.load(fp)
        except FileNotFoundError:
            raw = {}
        return cls(
            mode=raw.get("mode", "external"),
            public_url=(raw.get("public_url") or "").rstrip("/"),
            certfile=raw.get("certfile", "fullchain.pem"),
            keyfile=raw.get("keyfile", "privkey.pem"),
            install_integration=raw.get("install_integration", True),
            log_level=raw.get("log_level", "info"),
        )
