# Strava

Runs come from Strava through OAuth plus polling every 30 minutes (E10). Nothing is exposed to the internet: the
OAuth redirect happens in your browser, which is on the tailnet.

## 1. The Strava API app

Strava allows one API app per account, so reuse the one RunningCoach already has:
<https://www.strava.com/settings/api>.

- **Authorization Callback Domain:** `biggyserver.tailfff1d3.ts.net` (the host only: no `https://`, no path).
  Strava always accepts `localhost` and `127.0.0.1` as well, so scripts that authorize against localhost keep
  working.
- Note the **Client ID** and **Client Secret**.

## 2. Server

Add both keys to `.env` (`PUBLIC_BASE_URL` is already set to the tailnet URL), then restart the app:

```sh
STRAVA_CLIENT_ID=12345
STRAVA_CLIENT_SECRET=...
```

```sh
docker compose up -d app
```

## 3. Connect

1. Open the app on the tailnet: **Nastavení → Strava → Propojit Stravu**.
2. On Strava's page, keep the box for private activities ticked. The app asks for `activity:read_all`, and
   without `activity:read` the connection is refused with `?strava=missing_scope`.
3. Strava sends you back to **Nastavení**, which now shows *Propojeno · poslední synchronizace …*.

The first sync pages through the whole history. After that the scheduler syncs every 30 minutes, and
**Synchronizovat teď** syncs on demand. Per-second streams for the run metrics (GAP, EF, decoupling, time in
LTHR zones) are backfilled in small batches that stay well inside Strava's rate limits, so older runs get their
metrics over the following hours. The sync message shows how many are left (`zbývá N`).

## Check

- **Nastavení** shows the last sync time.
- The **Běh** page lists runs, with metric chips once their streams are in.
- `docker compose logs app | grep -i strava` shows no errors.

## Notes

- RunningCoach and the app use the same Strava app. If RunningCoach's own Strava access stops working after you
  connect here, authorize it there again.
- To disconnect, revoke the app at <https://www.strava.com/settings/apps>. Syncs then fail with "connect again",
  but the stored token stays, so **Nastavení** still says *Propojeno*. To connect again, open
  `https://biggyserver.tailfff1d3.ts.net/api/integrations/strava/connect` directly.
