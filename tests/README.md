# Tests

`test_bridge_smoke.py` runs against a Home Assistant core checkout's test
harness (it needs core's `tests/` fixtures):

```bash
# from a home-assistant/core checkout with a dev venv (script/setup)
ln -s /path/to/google-home-bridge/google_home_bridge/rootfs/opt/bridge/custom_components/cloud \
      tests/testing_config/custom_components/cloud
cp /path/to/google-home-bridge/tests/test_bridge_smoke.py tests/
.venv/bin/python -m pytest tests/test_bridge_smoke.py -q
rm tests/test_bridge_smoke.py tests/testing_config/custom_components/cloud
```

Covers:

- `cloud/status` reports logged-in + google_enabled (drives the native expose UI)
- `cloud/google_assistant/entities` lists supported entities
- `cloud/bridge/config` / `cloud/bridge/update_config` roundtrip
- `POST /api/google_assistant` answers a SYNC intent with default-exposed devices
- the native `homeassistant/expose_entity` toggle removes a device from SYNC
