"""Websocket + HTTP API mirroring the cloud integration's frontend surface."""

from __future__ import annotations

from collections.abc import Mapping
from contextlib import suppress
from http import HTTPStatus
import logging
from typing import Any

from aiohttp import web
import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.google_assistant import helpers as google_helpers
from homeassistant.components.google_assistant.http import (
    _get_homegraph_jwt,
    _get_homegraph_token,
)
from homeassistant.components.homeassistant import exposed_entities
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

from .const import (
    BRIDGE_EMAIL,
    CLOUD_GOOGLE,
    DATA_BRIDGE,
    PREF_DISABLE_2FA,
    PREF_ENABLE_GOOGLE,
    PREF_GOOGLE_REPORT_STATE,
    PREF_GOOGLE_SECURE_DEVICES_PIN,
)

_LOGGER = logging.getLogger(__name__)

_EMPTY_FILTER = {
    "include_domains": [],
    "include_entities": [],
    "exclude_domains": [],
    "exclude_entities": [],
}

_NOT_SUPPORTED = (
    "Not available: this instance uses the Google Home Bridge add-on instead of "
    "Home Assistant Cloud"
)


def async_setup(hass: HomeAssistant) -> None:
    """Register websocket commands and views."""
    websocket_api.async_register_command(hass, websocket_cloud_status)
    websocket_api.async_register_command(hass, websocket_subscription)
    websocket_api.async_register_command(hass, websocket_update_prefs)
    websocket_api.async_register_command(hass, websocket_remove_data)
    websocket_api.async_register_command(hass, websocket_hook_create)
    websocket_api.async_register_command(hass, websocket_hook_delete)
    websocket_api.async_register_command(hass, websocket_remote_connect)
    websocket_api.async_register_command(hass, websocket_remote_disconnect)
    websocket_api.async_register_command(hass, google_assistant_get)
    websocket_api.async_register_command(hass, google_assistant_list)
    websocket_api.async_register_command(hass, google_assistant_update)
    websocket_api.async_register_command(hass, alexa_get)
    websocket_api.async_register_command(hass, alexa_list)
    websocket_api.async_register_command(hass, alexa_sync)
    websocket_api.async_register_command(hass, tts_info)
    websocket_api.async_register_command(hass, bridge_config)
    websocket_api.async_register_command(hass, bridge_update_config)
    websocket_api.async_register_command(hass, bridge_sync)

    hass.http.register_view(GoogleActionsSyncView)


def _status(hass: HomeAssistant) -> dict[str, Any]:
    """Build the cloud/status payload the frontend expects."""
    bridge = hass.data[DATA_BRIDGE]
    assert hass.config.api
    return {
        "alexa_entities": dict(_EMPTY_FILTER),
        "alexa_registered": False,
        "bridge": True,
        "cloud": "connected",
        "cloud_last_disconnect_reason": None,
        "email": BRIDGE_EMAIL,
        "google_entities": dict(_EMPTY_FILTER),
        "google_registered": len(bridge.gconf.async_get_agent_users()) > 0,
        "google_local_connected": bridge.gconf.is_local_connected,
        "logged_in": True,
        "prefs": bridge.prefs.as_dict(),
        "onboarding_completed": True,
        "onboarding_postponed": False,
        "remote_certificate": None,
        "remote_certificate_status": None,
        "remote_connected": False,
        "remote_domain": None,
        "http_use_ssl": hass.config.api.use_ssl,
        "active_subscription": True,
    }


@websocket_api.websocket_command({vol.Required("type"): "cloud/status"})
@websocket_api.async_response
async def websocket_cloud_status(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle cloud status request."""
    connection.send_result(msg["id"], _status(hass))


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "cloud/subscription"})
@websocket_api.async_response
async def websocket_subscription(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle subscription info request."""
    connection.send_result(
        msg["id"],
        {
            "provider": "google_home_bridge",
            "plan": "self-hosted",
            "human_description": "Self-hosted (Google Home Bridge add-on)",
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "cloud/update_prefs",
        vol.Optional(PREF_ENABLE_GOOGLE): bool,
        vol.Optional(PREF_GOOGLE_REPORT_STATE): bool,
        vol.Optional(PREF_GOOGLE_SECURE_DEVICES_PIN): vol.Any(None, str),
        vol.Optional("alexa_enabled"): bool,
        vol.Optional("alexa_report_state"): bool,
        vol.Optional("cloud_ice_servers_enabled"): bool,
        vol.Optional("remote_allow_remote_enable"): bool,
        vol.Optional("tts_default_voice"): object,
    }
)
@websocket_api.async_response
async def websocket_update_prefs(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Handle preference updates; non-Google prefs are ignored."""
    bridge = hass.data[DATA_BRIDGE]
    changes = {
        key: msg[key]
        for key in (
            PREF_ENABLE_GOOGLE,
            PREF_GOOGLE_REPORT_STATE,
            PREF_GOOGLE_SECURE_DEVICES_PIN,
        )
        if key in msg
    }
    if changes:
        await bridge.prefs.async_update(**changes)
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "cloud/remove_data"})
@websocket_api.async_response
async def websocket_remove_data(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """No cloud data to remove."""
    connection.send_result(msg["id"])


def _not_supported(
    connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    connection.send_error(msg["id"], websocket_api.ERR_NOT_SUPPORTED, _NOT_SUPPORTED)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "cloud/cloudhook/create", vol.Required("webhook_id"): str}
)
@websocket_api.async_response
async def websocket_hook_create(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Cloudhooks are not supported."""
    _not_supported(connection, msg)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {vol.Required("type"): "cloud/cloudhook/delete", vol.Required("webhook_id"): str}
)
@websocket_api.async_response
async def websocket_hook_delete(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Cloudhooks are not supported."""
    _not_supported(connection, msg)


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "cloud/remote/connect"})
@websocket_api.async_response
async def websocket_remote_connect(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remote UI is not supported."""
    _not_supported(connection, msg)


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "cloud/remote/disconnect"})
@websocket_api.async_response
async def websocket_remote_disconnect(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Remote UI is not supported."""
    _not_supported(connection, msg)


@websocket_api.require_admin
@websocket_api.websocket_command(
    {"type": "cloud/google_assistant/entities/get", "entity_id": str}
)
@websocket_api.async_response
async def google_assistant_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Get data for a single google assistant entity."""
    bridge = hass.data[DATA_BRIDGE]
    entity_id: str = msg["entity_id"]
    state = hass.states.get(entity_id)

    if not state:
        connection.send_error(
            msg["id"], websocket_api.ERR_NOT_FOUND, f"{entity_id} unknown"
        )
        return

    entity = google_helpers.GoogleEntity(hass, bridge.gconf, state)
    if not entity.is_supported():
        connection.send_error(
            msg["id"],
            websocket_api.ERR_NOT_SUPPORTED,
            f"{entity_id} not supported by Google assistant",
        )
        return

    assistant_options: Mapping[str, Any] = {}
    with suppress(HomeAssistantError, KeyError):
        settings = exposed_entities.async_get_entity_settings(hass, entity_id)
        assistant_options = settings[CLOUD_GOOGLE]

    connection.send_result(
        msg["id"],
        {
            "entity_id": entity.entity_id,
            "traits": [trait.name for trait in entity.traits()],
            "might_2fa": entity.might_2fa_traits(),
            PREF_DISABLE_2FA: assistant_options.get(PREF_DISABLE_2FA),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "cloud/google_assistant/entities"})
@websocket_api.async_response
async def google_assistant_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """List all google assistant entities."""
    bridge = hass.data[DATA_BRIDGE]
    entities = google_helpers.async_get_entities(hass, bridge.gconf)

    connection.send_result(
        msg["id"],
        [
            {
                "entity_id": entity.entity_id,
                "traits": [trait.name for trait in entity.traits()],
                "might_2fa": entity.might_2fa_traits(),
            }
            for entity in entities
        ],
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        "type": "cloud/google_assistant/entities/update",
        "entity_id": str,
        vol.Optional(PREF_DISABLE_2FA): bool,
    }
)
@websocket_api.async_response
async def google_assistant_update(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update google assistant entity config."""
    entity_id: str = msg["entity_id"]

    assistant_options: Mapping[str, Any] = {}
    with suppress(HomeAssistantError, KeyError):
        settings = exposed_entities.async_get_entity_settings(hass, entity_id)
        assistant_options = settings[CLOUD_GOOGLE]

    disable_2fa = msg[PREF_DISABLE_2FA]
    if assistant_options.get(PREF_DISABLE_2FA) == disable_2fa:
        connection.send_result(msg["id"])
        return

    exposed_entities.async_set_assistant_option(
        hass, CLOUD_GOOGLE, entity_id, PREF_DISABLE_2FA, disable_2fa
    )
    connection.send_result(msg["id"])


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "cloud/alexa/entities/get", "entity_id": str})
@websocket_api.async_response
async def alexa_get(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Alexa is not supported by the bridge."""
    _not_supported(connection, msg)


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "cloud/alexa/entities"})
@websocket_api.async_response
async def alexa_list(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return no Alexa entities."""
    connection.send_result(msg["id"], [])


@websocket_api.require_admin
@websocket_api.websocket_command({"type": "cloud/alexa/sync"})
@websocket_api.async_response
async def alexa_sync(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Alexa is not supported by the bridge."""
    _not_supported(connection, msg)


@websocket_api.websocket_command({"type": "cloud/tts/info"})
def tts_info(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Cloud TTS is not supported by the bridge."""
    connection.send_result(msg["id"], {"languages": []})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "cloud/bridge/config"})
@websocket_api.async_response
async def bridge_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Return the bridge configuration for the add-on wizard."""
    bridge = hass.data[DATA_BRIDGE]
    prefs = bridge.prefs
    service_account = prefs.service_account or {}
    connection.send_result(
        msg["id"],
        {
            "project_id": prefs.project_id,
            "public_url": prefs.public_url,
            "has_service_account": prefs.service_account is not None,
            "service_account_email": service_account.get("client_email"),
            "google_enabled": prefs.google_enabled,
            "report_state": prefs.google_report_state,
            "agent_users": list(bridge.gconf.async_get_agent_users()),
            "exposed_entity_count": len(
                google_helpers.async_get_entities(hass, bridge.gconf)
            ),
        },
    )


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): "cloud/bridge/update_config",
        vol.Optional("project_id"): vol.Any(None, str),
        vol.Optional("public_url"): vol.Any(None, str),
        vol.Optional("service_account"): vol.Any(
            None,
            vol.Schema(
                {
                    vol.Required("client_email"): str,
                    vol.Required("private_key"): str,
                },
                extra=vol.ALLOW_EXTRA,
            ),
        ),
    }
)
@websocket_api.async_response
async def bridge_update_config(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Update bridge configuration, validating the service account if given."""
    bridge = hass.data[DATA_BRIDGE]
    changes = {
        key: msg[key]
        for key in ("project_id", "public_url", "service_account")
        if key in msg
    }

    if (service_account := changes.get("service_account")) is not None:
        try:
            token = await _get_homegraph_token(
                hass,
                _get_homegraph_jwt(
                    dt_util.utcnow(),
                    service_account["client_email"],
                    service_account["private_key"],
                ),
            )
        except Exception as err:  # noqa: BLE001 - report any failure to the wizard
            connection.send_error(
                msg["id"],
                "invalid_service_account",
                f"HomeGraph token exchange failed: {err}",
            )
            return
        if "access_token" not in token:
            connection.send_error(
                msg["id"],
                "invalid_service_account",
                "HomeGraph token exchange returned no access token",
            )
            return

    await bridge.prefs.async_update(**changes)
    connection.send_result(msg["id"], {"validated": "service_account" in changes})


@websocket_api.require_admin
@websocket_api.websocket_command({vol.Required("type"): "cloud/bridge/sync"})
@websocket_api.async_response
async def bridge_sync(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Trigger a requestSync for all linked Google accounts."""
    bridge = hass.data[DATA_BRIDGE]
    status = await bridge.gconf.async_sync_entities_all()
    if status == HTTPStatus.OK:
        connection.send_result(msg["id"])
    else:
        connection.send_error(msg["id"], "sync_failed", f"requestSync returned {status}")


class GoogleActionsSyncView(HomeAssistantView):
    """Trigger a Google Actions sync, used by the frontend sync button."""

    url = "/api/cloud/google_actions/sync"
    name = "api:cloud:google_actions/sync"

    async def post(self, request: web.Request) -> web.Response:
        """Trigger a Google Actions sync."""
        hass = request.app[KEY_HASS]
        bridge = hass.data[DATA_BRIDGE]
        status = await bridge.gconf.async_sync_entities_all()
        return self.json({}, status_code=status)
