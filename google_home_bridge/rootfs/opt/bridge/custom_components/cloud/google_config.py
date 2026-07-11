"""Google Assistant configuration backed by local credentials.

Reuses the manual google_assistant integration's transport (HomeGraph JWT,
report state, request sync, agent-user store, local SDK webhooks) but takes
entity exposure and 2FA settings from the native exposed-entities registry —
the same UX as Home Assistant Cloud.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import logging
from typing import Any

from homeassistant.components.google_assistant.const import (
    CONF_CLIENT_EMAIL,
    CONF_PRIVATE_KEY,
    CONF_REPORT_STATE,
    CONF_SERVICE_ACCOUNT,
    DEFAULT_EXPOSED_DOMAINS,
)
from homeassistant.components.google_assistant.http import GoogleConfig
from homeassistant.components.homeassistant.exposed_entities import (
    async_expose_entity,
    async_get_entity_settings,
    async_listen_entity_updates,
    async_should_expose,
)
from homeassistant.core import (
    CoreState,
    Event,
    HomeAssistant,
    State,
    callback,
    split_entity_id,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import (
    device_registry as dr,
    entity_registry as er,
    start,
)

from .const import CLOUD_GOOGLE, DEFAULT_DISABLE_2FA, PREF_DISABLE_2FA
from .prefs import BridgePreferences

_LOGGER = logging.getLogger(__name__)


def _build_ga_config(prefs: BridgePreferences) -> dict[str, Any]:
    """Build the config dict the manual GoogleConfig transport expects."""
    config: dict[str, Any] = {CONF_REPORT_STATE: prefs.google_report_state}
    if (service_account := prefs.service_account) is not None:
        config[CONF_SERVICE_ACCOUNT] = {
            CONF_CLIENT_EMAIL: service_account["client_email"],
            CONF_PRIVATE_KEY: service_account["private_key"],
        }
    return config


class BridgeGoogleConfig(GoogleConfig):
    """Google config with exposed-entities-registry driven exposure."""

    def __init__(self, hass: HomeAssistant, prefs: BridgePreferences) -> None:
        """Initialize the config."""
        super().__init__(hass, _build_ga_config(prefs))
        self._prefs = prefs
        self._sync_lock = asyncio.Lock()

    async def async_initialize(self) -> None:
        """Perform async initialization of config."""
        await super().async_initialize()

        # The parent enables the local SDK unconditionally (manual setup is
        # always enabled); keep it in step with our enabled pref. Google
        # falls back to cloud fulfillment per command when local is off.
        if not self.enabled and self.is_local_sdk_active:
            self.async_disable_local_sdk()

        async def on_hass_started(hass: HomeAssistant) -> None:
            if not self._prefs.settings_migrated:
                self._async_migrate_default_expose()
                await self._prefs.async_update(settings_migrated=True)
            self._on_deinitialize.append(
                async_listen_entity_updates(
                    self.hass, CLOUD_GOOGLE, self._async_exposed_entities_updated
                )
            )

        self._on_deinitialize.append(
            start.async_at_started(self.hass, on_hass_started)
        )
        self._on_deinitialize.append(
            self._prefs.async_listen_updates(self._async_prefs_updated)
        )
        self._on_deinitialize.append(
            self.hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED,
                self._handle_entity_registry_updated,
            )
        )
        self._on_deinitialize.append(
            self.hass.bus.async_listen(
                dr.EVENT_DEVICE_REGISTRY_UPDATED,
                self._handle_device_registry_updated,
            )
        )

        if self.enabled and self.should_report_state:
            self.async_enable_report_state()

    @property
    def enabled(self) -> bool:
        """Return if Google is enabled."""
        return self._prefs.google_enabled

    @property
    def entity_config(self) -> dict[str, Any]:
        """Return per-entity YAML config (unused, registry drives exposure)."""
        return {}

    @property
    def secure_devices_pin(self) -> str | None:
        """Return the secure devices PIN."""
        return self._prefs.google_secure_devices_pin

    @property
    def should_report_state(self) -> bool:
        """Return if states should be proactively reported."""
        return (
            self.enabled
            and self._prefs.google_report_state
            and self._prefs.service_account is not None
        )

    @callback
    def _async_migrate_default_expose(self) -> None:
        """Expose supported entities on first run.

        Mirrors the cloud integration's v1 settings migration: without it a
        fresh install would sync zero devices, because expose_new defaults to
        off for cloud assistants in the exposed-entities registry.
        """
        entity_registry = er.async_get(self.hass)
        for entity_id in self.hass.states.async_entity_ids():
            registry_entry = entity_registry.async_get(entity_id)
            auxiliary = registry_entry is not None and (
                registry_entry.entity_category is not None
                or registry_entry.hidden_by is not None
            )
            expose = (
                split_entity_id(entity_id)[0] in DEFAULT_EXPOSED_DOMAINS
                and not auxiliary
            )
            async_expose_entity(self.hass, CLOUD_GOOGLE, entity_id, expose)
        _LOGGER.info("Applied default Google Assistant exposure to existing entities")

    def should_expose(self, entity_id: str) -> bool:
        """Return if an entity should be exposed, from the native registry."""
        return async_should_expose(self.hass, CLOUD_GOOGLE, entity_id)

    def should_2fa(self, state: State) -> bool:
        """Return if an entity should be checked for 2FA."""
        try:
            settings = async_get_entity_settings(self.hass, state.entity_id)
        except HomeAssistantError:
            return False

        assistant_options = settings.get(CLOUD_GOOGLE, {})
        return not assistant_options.get(PREF_DISABLE_2FA, DEFAULT_DISABLE_2FA)

    async def _async_request_sync_devices(self, agent_user_id: str) -> HTTPStatus:
        if self._sync_lock.locked():
            return HTTPStatus.OK
        async with self._sync_lock:
            return await super()._async_request_sync_devices(agent_user_id)

    async def _async_prefs_updated(self, prefs: BridgePreferences) -> None:
        """Handle updated preferences."""
        self._config = _build_ga_config(prefs)
        # Credentials changed — force a token refresh on next HomeGraph call.
        self._access_token = None

        sync_entities = False

        if self.should_report_state != self.is_reporting_state:
            if self.should_report_state:
                self.async_enable_report_state()
            else:
                self.async_disable_report_state()
            sync_entities = True

        if self.enabled and not self.is_local_sdk_active:
            self.async_enable_local_sdk()
            sync_entities = True
        elif not self.enabled and self.is_local_sdk_active:
            self.async_disable_local_sdk()
            sync_entities = True

        if sync_entities and self.hass.is_running:
            await self.async_sync_entities_all()

    @callback
    def _async_exposed_entities_updated(self) -> None:
        """Handle updated exposed entities registry."""
        self.async_schedule_google_sync_all()

    @callback
    def _handle_entity_registry_updated(
        self, event: Event[er.EventEntityRegistryUpdatedData]
    ) -> None:
        """Handle when entity registry updated."""
        if not self.enabled or self.hass.state is not CoreState.running:
            return

        if event.data["action"] == "update" and not bool(
            set(event.data["changes"]) & er.ENTITY_DESCRIBING_ATTRIBUTES
        ):
            return

        if not self.should_expose(event.data["entity_id"]):
            return

        self.async_schedule_google_sync_all()

    @callback
    def _handle_device_registry_updated(
        self, event: Event[dr.EventDeviceRegistryUpdatedData]
    ) -> None:
        """Handle when device registry updated."""
        if not self.enabled or self.hass.state is not CoreState.running:
            return

        # Device registry is only used for area changes.
        if event.data["action"] != "update" or "area_id" not in event.data["changes"]:
            return

        if not any(
            entity_entry.area_id is None and self.should_expose(entity_entry.entity_id)
            for entity_entry in er.async_entries_for_device(
                er.async_get(self.hass), event.data["device_id"]
            )
        ):
            return

        self.async_schedule_google_sync_all()
