# Google Home Bridge

Self-hosted replacement for the **Google Assistant part of Home Assistant
Cloud (Nabu Casa)**. After setup, the experience is identical to a
subscription: you toggle entities in **Settings → Voice assistants →
Expose**, states report to Google in real time, and "Hey Google, turn on the
lights" just works — but all traffic flows through *your* Google project and
*your* endpoint.

## How it works

The add-on ships two parts:

1. **A cloud shim integration** (installed into
   `/config/custom_components/cloud`). It shadows the built-in `cloud`
   integration and provides the native Google Assistant UI (expose toggles,
   2FA settings, sync button) plus direct HomeGraph API calls (report state,
   request sync) using your own service account. Alexa, Remote UI, cloud
   TTS/STT and cloudhooks are **not** provided — this is a Google-only
   replacement.
2. **A selective public proxy.** Google only ever needs three things from
   your instance: the fulfillment endpoint (`/api/google_assistant`), the
   login page for account linking (`/auth/authorize` + assets) and the OAuth
   token endpoint (`/auth/token`). The proxy exposes exactly those and rejects
   everything else.

## Setup

Everything below is guided interactively by the add-on's web UI (open the
add-on page and click **Open Web UI**), including copy-paste values and
validation buttons. Summary:

### 1. Choose an exposure mode

| Mode | What it does | Needs |
|---|---|---|
| `external` (default) | You publish Home Assistant over HTTPS yourself — tunnel add-on (e.g. Cloudflared), reverse proxy, VPN edge, … | Existing public HTTPS |
| `direct` | Serves TLS itself on port 8124 using certificates from `/ssl`. | Port forward 443 → 8124, certs (e.g. Let's Encrypt/DuckDNS add-on) |

> **Security note:** in `direct` mode only the allow-listed paths (login +
> fulfillment) are public. In `external` mode your proxy decides what is
> exposed — for the same allow-list filtering, point your tunnel/proxy at
> this add-on on port `8124` (plain HTTP, add-on network) instead of at
> Home Assistant.

### 2. Trust the proxy

Add to `configuration.yaml` and restart (the wizard shows this too):

```yaml
http:
  use_x_forwarded_for: true
  trusted_proxies:
    - 172.30.32.0/23
```

Without it, failed login attempts from anywhere on the internet are all
attributed to the add-on's IP and Home Assistant's IP ban can lock the bridge
out.

### 3. Create your Google project

In the [Google Home Developer Console](https://console.home.google.com/):
create a project, add a **Cloud-to-cloud** integration, and paste the
fulfillment/OAuth values the wizard generates:

- Fulfillment URL: `https://YOUR_PUBLIC_URL/api/google_assistant`
- Authorization URL: `https://YOUR_PUBLIC_URL/auth/authorize`
- Token URL: `https://YOUR_PUBLIC_URL/auth/token`
- Client ID: `https://oauth-redirect.googleusercontent.com/r/YOUR_PROJECT_ID`
- Client secret: anything

### 4. Service account (live state reporting)

In Google Cloud Console (same project): enable the **HomeGraph API**, create
a service account key (JSON), paste it into the wizard. The wizard validates
it against Google before saving. Without it, voice commands still work but
the Google Home app won't show live states and the sync button is
unavailable.

### 5. Link

Google Home app → **+** → **Link app or service** → **Works with Google** →
search for `[test] your project`. Log in with your Home Assistant account.
Done.

## Exposure behavior

On first activation the shim exposes all existing entities in Google's
default domains (lights, switches, covers, climate, media players, …),
matching a fresh Nabu Casa setup. Entities added later follow the **"Expose
new entities"** toggle on the expose page (off by default for Google, same
as Cloud). Everything is adjustable per entity in
**Settings → Voice assistants → Expose**.

## Migrating from Nabu Casa

Entity expose/2FA settings live in Home Assistant's own registry, not in
Nabu Casa — they carry over automatically in both directions. To migrate:
unlink "Home Assistant" in the Google Home app, set up this add-on, link your
test action. To go back: delete `/config/custom_components/cloud`, restart,
re-link Nabu Casa.

## Limitations

- Google requires the linked action to stay in "[test]" state — that's fine,
  test deployments don't expire for smart home actions, but the `[test]`
  prefix shows in the Google Home app during linking.
- Alexa, Remote UI, cloud TTS/STT and cloudhooks are not replaced.
- Local fulfillment (LAN path) is not yet wired up; commands take the cloud
  round-trip (typically ~300–600 ms).
- A manual `google_assistant:` section in `configuration.yaml` conflicts with
  the bridge — remove it.

## Troubleshooting

- **No Google Assistant column under Voice assistants** — the shim isn't
  active: check the wizard status card, restart Home Assistant.
- **Account linking fails immediately** — public URL wrong or proxy blocked;
  use the wizard's reachability test (expects `/auth/providers` → 200 and
  `/api/google_assistant` → 401).
- **Devices don't update in the app** — service account missing/invalid, or
  the HomeGraph API isn't enabled for the project.
- **`429` or ban messages in the HA log** — you skipped step 2
  (trusted_proxies).
