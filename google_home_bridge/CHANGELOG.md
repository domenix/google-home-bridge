# Changelog

## 1.1.1

- Wizard step 4: explicit service-account walkthrough (skip role/principals,
  Keys → JSON key)

## 1.1.0

- **Breaking:** built-in cloudflared removed — run a tunnel with a dedicated
  add-on (e.g. Cloudflared) or any reverse proxy instead. `mode` now
  defaults to `external`; `cloudflared_token` option dropped. Existing
  installs with `mode: cloudflared` must switch to `external` or `direct`.
- Smaller image (no cloudflared binary), simpler config

## 1.0.1

- Wizard: per-mode setup help in step 1 (cloudflared token walkthrough,
  direct/external one-liners), "Tunnel: no token" status pill
- Wizard: step 3 reordered to match the Google Home Developer Console form
  top to bottom, project ID field moved first
- Wizard: placeholder app icon generator (144×144 PNG named after project ID)

## 1.0.0

- Initial release
- Cloud shim integration: native expose UI, report state, request sync,
  2FA settings, Google Home app sync button
- Selective public proxy with cloudflared / direct TLS / external modes
- Ingress setup wizard with reachability + service-account validation
