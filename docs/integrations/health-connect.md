# Watch steps and sleep (Health Connect)

The Galaxy Watch writes into Samsung Health on the Android phone it's paired with. Samsung Health copies that
into Health Connect, and **Life Dashboard Companion** (MIT, by owen282000) forwards it to
`POST /api/webhooks/health-connect` (E8, O2, SPEC §6.5).

The server keeps every raw record by its `uuid` and rebuilds each touched day, so repeated, edited or late
payloads are harmless. Only records written by Samsung Health count (`HEALTH_CONNECT_ORIGINS`), so another app
writing the same steps can't double them.

## Before you start

- **Tailscale** on the Android phone, logged in to the same tailnet, set as *Always-on VPN* (Android
  Settings → Connections → More connection settings → VPN → ⚙ next to Tailscale).
- The webhook token. On the server: `grep '^WEBHOOK_TOKEN=' .env`.

## 1. Samsung Health → Health Connect

Samsung Health → **Settings → Health Connect**: allow Samsung Health to write **Steps** and **Sleep**. On
Android 14+ Health Connect is part of the system (Settings → Security and privacy → Health Connect); on older
Android, install it from the Play Store.

## 2. Install the app

Install from <https://github.com/owen282000/life-dashboard-companion-app/releases/latest> (signed APK), or add
the repo to **Obtainium** so it stays up to date. F-Droid accepted the app on 2026-10-17 and lists it once its
build server has picked it up.

## 3. Setup wizard

1. *What do you want to sync?* **Health Connect** (screen time isn't used).
2. *Where should your data go?* **Webhook**, URL
   `https://biggyserver.tailfff1d3.ts.net/api/webhooks/health-connect`. The wizard's test ping fails with
   **401** at this point, because the token header is only added in step 4. That's expected.
3. *Which health data?* **Decide later**. Next, turn on only **Steps** and **Sleep**.

## 4. Settings on the Health tab

- **Grant** on the top card. In Health Connect's screen allow *Steps* and *Sleep*, and **reading in the
  background** (without it, only *Sync Now* with the app open works).
- **Webhook → Webhook Headers**: add `X-Webhook-Token` with the token. Alternatively set an **HMAC signing
  secret** and put the same value into `HEALTH_CONNECT_SECRET` in `.env` (then `docker compose up -d app`). One
  of the two is enough; the server checks the signature when both a secret and an `X-Signature` header are there,
  otherwise the token. Tap **Test ping**: it should now succeed (the server answers 200 and ignores pings).
  Then **Save Changes**.
- **Data Resolution**: leave Steps at **every record** (the default). The server merges phone and watch in its
  own 15-minute buckets and needs each record's start and end.
- **Advanced → Daily totals in payload**: leave on. The server stores them as the watch's daily total.
- **Sync Schedule**: the default of every 60 minutes is fine.

## 5. Keep Android from killing the sync (Samsung phone)

1. Settings → Apps → **Life Dashboard → Battery → Unrestricted**.
2. Settings → Battery (or Device care) → **Background usage limits → Never sleeping apps** → add Life Dashboard.

## 6. First sync and backfill

1. **Sync Now**. The line below it should say *Synced N records*.
2. **Backfill** → **Grant history access** first, then **365d**. It sends a year in 3-day chunks in the
   background and can take a while.

## Check

- **Nastavení → Zdroje kroků a spánku** shows *Hodinky (Health Connect)* with the time of the last payload.
- Dashboard → **Kroky dnes** → detail shows *Hodinky* next to *iPhone*, with the method *po 15 min vyšší z obou
  zdrojů, sečteno* on days when both carried data.
- Sleep shows up on the day you woke up. Nightly sleep arrives only after Samsung Health writes it in the
  morning, often an hour or more after waking.
- Server side: `docker compose logs app | grep health-connect`.

| Symptom | Cause |
|---|---|
| *Server unreachable – N records queued* | Tailscale is off on the phone. The app retries on the next sync. |
| 401 in the app's **Logs** | Header name or token mistyped, or a signing secret set in the app but not in `.env`. |
| 503 | `WEBHOOK_TOKEN` is not set on the server. |
| Syncs only happen when the app is opened | Battery settings from step 5. |
| Steps arrive but sleep doesn't | Sleep permission missing in Health Connect, or Samsung Health doesn't write sleep to Health Connect (step 1). The watch isn't worn at night (RunningCoach facts), so missing sleep can be genuine. |
