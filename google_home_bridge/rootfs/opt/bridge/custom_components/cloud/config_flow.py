"""Config flow for the Cloud integration.

Mirrors the core cloud integration's system config flow so the config entry
created by Home Assistant Cloud keeps loading against this shim.
"""

from typing import Any

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN


class CloudConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the Cloud integration."""

    VERSION = 1

    async def async_step_system(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the system step."""
        return self.async_create_entry(title="Home Assistant Cloud", data={})
