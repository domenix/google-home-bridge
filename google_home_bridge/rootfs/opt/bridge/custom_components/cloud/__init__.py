"""Google Home Bridge — self-hosted replacement for Home Assistant Cloud's Google integration.

This custom integration shadows the core `cloud` integration (same domain) so
the native frontend experience keeps working without a Nabu Casa subscription:

- The voice assistants expose UI (Settings -> Voice assistants) shows the
  Google Assistant column because `cloud/status` reports logged_in with
  google_enabled.
- Per-entity expose toggles and 2FA settings use the same exposed-entities
  registry key (`cloud.google_assistant`) as Home Assistant Cloud, so existing
  settings survive migration in both directions.
- Google smart-home intents arrive on `/api/google_assistant` (HA bearer-token
  auth via OAuth account linking), served by the core google_assistant engine.
- Report state / request sync call the HomeGraph API directly with the user's
  own service account.

The module-level helper API used by other integrations (cloudhooks, remote UI,
account linking) intentionally reports "cloud not available" so those features
fall back to their non-cloud paths — only the Google Assistant surface is
emulated.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components.google_assistant.http import GoogleAssistantView
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.typing import ConfigType

from . import http_api
from .const import DATA_BRIDGE, DOMAIN
from .google_config import BridgeGoogleConfig
from .prefs import BridgePreferences

_LOGGER = logging.getLogger(__name__)

CONFIG_SCHEMA = vol.Schema(
    {DOMAIN: vol.Schema({}, extra=vol.ALLOW_EXTRA)}, extra=vol.ALLOW_EXTRA
)


class CloudNotAvailable(HomeAssistantError):
    """Raised when an action requires the cloud but it's not available."""


class CloudNotConnected(CloudNotAvailable):
    """Raised when an action requires the cloud but it's not connected."""


class CloudConnectionState(Enum):
    """Cloud connection state."""

    CLOUD_CONNECTED = "cloud_connected"
    CLOUD_DISCONNECTED = "cloud_disconnected"


@callback
def async_is_logged_in(hass: HomeAssistant) -> bool:
    """Test if user is logged in.

    Reported False so integrations relying on Nabu Casa services (cloudhooks,
    account linking) use their local fallbacks.
    """
    return False


@callback
def async_is_connected(hass: HomeAssistant) -> bool:
    """Test if connected to the cloud."""
    return False


@callback
def async_listen_connection_change(
    hass: HomeAssistant,
    target: Callable[[CloudConnectionState], Awaitable[None] | None],
) -> Callable[[], None]:
    """Notify on connection state changes — never fires for the bridge."""
    return lambda: None


@callback
def async_active_subscription(hass: HomeAssistant) -> bool:
    """Test if user has an active subscription."""
    return False


async def async_get_or_create_cloudhook(hass: HomeAssistant, webhook_id: str) -> str:
    """Cloudhooks are not available with the bridge."""
    raise CloudNotAvailable


async def async_create_cloudhook(hass: HomeAssistant, webhook_id: str) -> str:
    """Cloudhooks are not available with the bridge."""
    raise CloudNotAvailable


async def async_delete_cloudhook(hass: HomeAssistant, webhook_id: str) -> None:
    """Cloudhooks are not available with the bridge."""
    raise CloudNotAvailable


@callback
def async_listen_cloudhook_change(
    hass: HomeAssistant,
    webhook_id: str,
    on_change: Callable[[dict[str, Any] | None], None],
) -> CALLBACK_TYPE:
    """Notify on cloudhook changes — never fires for the bridge."""
    return lambda: None


@callback
def async_remote_ui_url(hass: HomeAssistant) -> str:
    """Remote UI is not available with the bridge."""
    raise CloudNotAvailable


@dataclass
class BridgeData:
    """Runtime data for the bridge."""

    prefs: BridgePreferences
    gconf: BridgeGoogleConfig


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the Google Home Bridge cloud shim."""
    prefs = BridgePreferences(hass)
    await prefs.async_initialize()

    gconf = BridgeGoogleConfig(hass, prefs)
    await gconf.async_initialize()

    hass.data[DATA_BRIDGE] = BridgeData(prefs, gconf)

    try:
        hass.http.register_view(GoogleAssistantView(gconf))
    except Exception:
        _LOGGER.exception(
            "Could not register /api/google_assistant. If you have a manual "
            "'google_assistant:' section in configuration.yaml, remove it — "
            "the Google Home Bridge replaces it"
        )
        return False

    http_api.async_setup(hass)

    async def _noop_remote(call: ServiceCall) -> None:
        _LOGGER.warning(
            "Service %s.%s does nothing: remote UI is not available with the "
            "Google Home Bridge",
            DOMAIN,
            call.service,
        )

    hass.services.async_register(DOMAIN, "remote_connect", _noop_remote)
    hass.services.async_register(DOMAIN, "remote_disconnect", _noop_remote)

    _LOGGER.info("Google Home Bridge cloud shim is active")
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Accept the config entry left behind by Home Assistant Cloud.

    All actual setup happens in async_setup; the entry only exists so the
    migration back to Nabu Casa stays trivial.
    """
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload the config entry."""
    return True
