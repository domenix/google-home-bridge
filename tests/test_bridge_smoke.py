"""Smoke tests for the Google Home Bridge shadow cloud integration."""

from typing import Any

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component

from tests.typing import ClientSessionGenerator, WebSocketGenerator


@pytest.fixture(autouse=True)
def _enable_custom(enable_custom_integrations: None) -> None:
    """Load the custom cloud shim."""


async def _setup(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, "homeassistant", {})
    assert await async_setup_component(hass, "cloud", {"cloud": {}})
    await hass.async_block_till_done()


async def test_cloud_status_reports_logged_in(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """cloud/status must report a logged-in, google-enabled cloud."""
    await _setup(hass)
    client = await hass_ws_client(hass)

    await client.send_json({"id": 5, "type": "cloud/status"})
    msg = await client.receive_json()

    assert msg["success"], msg
    result = msg["result"]
    assert result["logged_in"] is True
    assert result["active_subscription"] is True
    assert result["bridge"] is True
    assert result["cloud"] == "connected"
    assert result["prefs"]["google_enabled"] is True
    assert result["prefs"]["alexa_enabled"] is False


async def test_google_entities_list(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """cloud/google_assistant/entities lists supported entities."""
    await _setup(hass)
    hass.states.async_set("light.kitchen", "on")
    client = await hass_ws_client(hass)

    await client.send_json({"id": 5, "type": "cloud/google_assistant/entities"})
    msg = await client.receive_json()

    assert msg["success"], msg
    entity_ids = [entry["entity_id"] for entry in msg["result"]]
    assert "light.kitchen" in entity_ids


async def test_bridge_config_roundtrip(
    hass: HomeAssistant, hass_ws_client: WebSocketGenerator
) -> None:
    """cloud/bridge/config + update_config store project settings."""
    await _setup(hass)
    client = await hass_ws_client(hass)

    await client.send_json(
        {
            "id": 5,
            "type": "cloud/bridge/update_config",
            "project_id": "my-project",
            "public_url": "https://example.com",
        }
    )
    msg = await client.receive_json()
    assert msg["success"], msg

    await client.send_json({"id": 6, "type": "cloud/bridge/config"})
    msg = await client.receive_json()
    assert msg["success"], msg
    assert msg["result"]["project_id"] == "my-project"
    assert msg["result"]["public_url"] == "https://example.com"
    assert msg["result"]["has_service_account"] is False


async def test_fulfillment_sync_intent(
    hass: HomeAssistant, hass_client: ClientSessionGenerator
) -> None:
    """POST /api/google_assistant answers a SYNC intent with devices."""
    hass.states.async_set("light.kitchen", "on")
    await _setup(hass)
    client = await hass_client()

    response = await client.post(
        "/api/google_assistant",
        json={
            "requestId": "req-1",
            "inputs": [{"intent": "action.devices.SYNC"}],
        },
    )
    assert response.status == 200
    body: dict[str, Any] = await response.json()
    device_ids = [
        device["id"] for device in body["payload"]["devices"]
    ]
    assert "light.kitchen" in device_ids


async def test_expose_toggle_controls_sync(
    hass: HomeAssistant,
    hass_ws_client: WebSocketGenerator,
    hass_client: ClientSessionGenerator,
) -> None:
    """Turning off the native expose toggle hides the entity from SYNC."""
    hass.states.async_set("light.kitchen", "on")
    await _setup(hass)

    ws = await hass_ws_client(hass)
    await ws.send_json(
        {
            "id": 5,
            "type": "homeassistant/expose_entity",
            "assistants": ["cloud.google_assistant"],
            "entity_ids": ["light.kitchen"],
            "should_expose": False,
        }
    )
    msg = await ws.receive_json()
    assert msg["success"], msg

    client = await hass_client()
    response = await client.post(
        "/api/google_assistant",
        json={"requestId": "req-2", "inputs": [{"intent": "action.devices.SYNC"}]},
    )
    assert response.status == 200
    body = await response.json()
    device_ids = [device["id"] for device in body["payload"].get("devices", [])]
    assert "light.kitchen" not in device_ids
