"""Constants for the Google Home Bridge shadow cloud integration."""

from __future__ import annotations

DOMAIN = "cloud"

STORAGE_KEY = "cloud_bridge"
STORAGE_VERSION = 1

PREF_ENABLE_GOOGLE = "google_enabled"
PREF_ENABLE_ALEXA = "alexa_enabled"
PREF_ENABLE_REMOTE = "remote_enabled"
PREF_GOOGLE_REPORT_STATE = "google_report_state"
PREF_ALEXA_REPORT_STATE = "alexa_report_state"
PREF_GOOGLE_SECURE_DEVICES_PIN = "google_secure_devices_pin"
PREF_DISABLE_2FA = "disable_2fa"
PREF_ALEXA_DEFAULT_EXPOSE = "alexa_default_expose"
PREF_GOOGLE_DEFAULT_EXPOSE = "google_default_expose"
PREF_CLOUDHOOKS = "cloudhooks"
PREF_ENABLE_CLOUD_ICE_SERVERS = "cloud_ice_servers_enabled"
PREF_ONBOARDED_ITEMS = "onboarded_items"
PREF_ONBOARDING_POSTPONED_UNTIL = "onboarding_postponed_until"
PREF_REMOTE_ALLOW_REMOTE_ENABLE = "remote_allow_remote_enable"
PREF_TTS_DEFAULT_VOICE = "tts_default_voice"

# Bridge specific settings
PREF_PROJECT_ID = "project_id"
PREF_SERVICE_ACCOUNT = "service_account"
PREF_PUBLIC_URL = "public_url"

DEFAULT_DISABLE_2FA = False

# Assistant key in homeassistant.exposed_entities — must stay identical to the
# real cloud integration so the native expose UI and stored settings work.
CLOUD_GOOGLE = "cloud.google_assistant"

DATA_BRIDGE = "cloud_bridge_data"

BRIDGE_EMAIL = "google-home-bridge@local"
