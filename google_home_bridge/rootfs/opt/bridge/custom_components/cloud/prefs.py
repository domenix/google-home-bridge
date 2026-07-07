"""Preference storage for the Google Home Bridge shadow cloud integration."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
import logging
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.storage import Store

from .const import (
    PREF_ALEXA_DEFAULT_EXPOSE,
    PREF_ALEXA_REPORT_STATE,
    PREF_CLOUDHOOKS,
    PREF_ENABLE_ALEXA,
    PREF_ENABLE_CLOUD_ICE_SERVERS,
    PREF_ENABLE_GOOGLE,
    PREF_ENABLE_REMOTE,
    PREF_GOOGLE_DEFAULT_EXPOSE,
    PREF_GOOGLE_REPORT_STATE,
    PREF_GOOGLE_SECURE_DEVICES_PIN,
    PREF_ONBOARDED_ITEMS,
    PREF_ONBOARDING_POSTPONED_UNTIL,
    PREF_PROJECT_ID,
    PREF_PUBLIC_URL,
    PREF_REMOTE_ALLOW_REMOTE_ENABLE,
    PREF_SERVICE_ACCOUNT,
    PREF_TTS_DEFAULT_VOICE,
    STORAGE_KEY,
    STORAGE_VERSION,
)

_LOGGER = logging.getLogger(__name__)

_DEFAULTS: dict[str, Any] = {
    PREF_ENABLE_GOOGLE: True,
    PREF_GOOGLE_REPORT_STATE: True,
    PREF_GOOGLE_SECURE_DEVICES_PIN: None,
    PREF_PROJECT_ID: None,
    PREF_SERVICE_ACCOUNT: None,
    PREF_PUBLIC_URL: None,
    PREF_ONBOARDED_ITEMS: [],
    PREF_ONBOARDING_POSTPONED_UNTIL: None,
}


class BridgePreferences:
    """Handle bridge preferences, persisted in .storage/cloud_bridge."""

    def __init__(self, hass: HomeAssistant) -> None:
        """Initialize preferences."""
        self._hass = hass
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, STORAGE_KEY)
        self._prefs: dict[str, Any] = {}
        self._listeners: list[
            Callable[[BridgePreferences], Awaitable[None]]
        ] = []

    async def async_initialize(self) -> None:
        """Load preferences."""
        if (prefs := await self._store.async_load()) is None:
            prefs = {}
        self._prefs = {**_DEFAULTS, **prefs}

    async def async_update(self, **kwargs: Any) -> None:
        """Update preferences and notify listeners."""
        self._prefs = {**self._prefs, **kwargs}
        await self._store.async_save(self._prefs)
        for listener in self._listeners:
            try:
                await listener(self)
            except Exception:
                _LOGGER.exception("Error in bridge prefs listener")

    @callback
    def async_listen_updates(
        self, listener: Callable[[BridgePreferences], Awaitable[None]]
    ) -> Callable[[], None]:
        """Listen for preference updates."""
        self._listeners.append(listener)

        def unsub() -> None:
            self._listeners.remove(listener)

        return unsub

    def as_dict(self) -> dict[str, Any]:
        """Return the preference dict the frontend expects from cloud/status."""
        return {
            PREF_ALEXA_DEFAULT_EXPOSE: [],
            PREF_ALEXA_REPORT_STATE: False,
            PREF_CLOUDHOOKS: {},
            PREF_ENABLE_ALEXA: False,
            PREF_ENABLE_CLOUD_ICE_SERVERS: False,
            PREF_ENABLE_GOOGLE: self.google_enabled,
            PREF_ENABLE_REMOTE: False,
            PREF_GOOGLE_DEFAULT_EXPOSE: [],
            PREF_GOOGLE_REPORT_STATE: self.google_report_state,
            PREF_GOOGLE_SECURE_DEVICES_PIN: self.google_secure_devices_pin,
            PREF_ONBOARDED_ITEMS: self._prefs.get(PREF_ONBOARDED_ITEMS, []),
            PREF_ONBOARDING_POSTPONED_UNTIL: self._prefs.get(
                PREF_ONBOARDING_POSTPONED_UNTIL
            ),
            PREF_REMOTE_ALLOW_REMOTE_ENABLE: False,
            PREF_TTS_DEFAULT_VOICE: None,
        }

    @property
    def google_enabled(self) -> bool:
        """Return if Google is enabled."""
        return bool(self._prefs.get(PREF_ENABLE_GOOGLE, True))

    @property
    def google_report_state(self) -> bool:
        """Return if Google report state is enabled."""
        return bool(self._prefs.get(PREF_GOOGLE_REPORT_STATE, True))

    @property
    def google_secure_devices_pin(self) -> str | None:
        """Return the secure devices PIN."""
        return self._prefs.get(PREF_GOOGLE_SECURE_DEVICES_PIN)

    @property
    def project_id(self) -> str | None:
        """Return the Google Actions project id."""
        return self._prefs.get(PREF_PROJECT_ID)

    @property
    def service_account(self) -> dict[str, Any] | None:
        """Return the HomeGraph service account info."""
        return self._prefs.get(PREF_SERVICE_ACCOUNT)

    @property
    def public_url(self) -> str | None:
        """Return the public URL of the bridge, informational only."""
        return self._prefs.get(PREF_PUBLIC_URL)

    @property
    def settings_migrated(self) -> bool:
        """Return if the one-time default exposure migration has run."""
        return bool(self._prefs.get("settings_migrated", False))

    @property
    def onboarding_completed(self) -> bool:
        """Return if cloud onboarding is completed."""
        return True

    @property
    def onboarding_postponed(self) -> bool:
        """Return if cloud onboarding is postponed."""
        return False
