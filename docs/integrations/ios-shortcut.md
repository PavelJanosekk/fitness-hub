# iPhone steps (iOS Shortcut)

Apple Health steps reach the app through a Shortcut that posts the iPhone's step samples to
`POST /api/webhooks/health` (E6, SPEC §6.5).

> **Not yet built on the real iPhone.** The action names below are the English ones (a Czech iPhone shows
> translated names). The server side has been tested with the payload shape this Shortcut is meant to produce.

## How it works

- Each run sends **every** step sample of **yesterday and today** with `source: apple_health`. The server
  **replaces** the iPhone's data for those two days, so runs are idempotent and a later run fixes an earlier one.
- Because of that replace rule, a run must never send an incomplete day: no limit on the samples, and a guard
  that stops when nothing was read.
- **iOS keeps Health data locked while the phone is locked.** A timed automation that fires in your pocket can't
  read the samples. It then stops without sending (the guard), so no data is lost, but nothing new arrives
  either. That's why there is also a trigger that fires while the phone is in use.
- Any successful run after midnight completes the previous day, so one good run a day is enough.

## Before you start

- **Tailscale** on the iPhone with **VPN On Demand** on, so the request reaches the server from anywhere.
- The webhook token. On the server: `grep '^WEBHOOK_TOKEN=' .env`. Copy the value after `=` (a password manager
  or Universal Clipboard avoids typing 43 characters).

## Build the Shortcut

Name it **Fitness Hub kroky**. Actions in order:

1. **Date**: *Current Date*.
2. **Adjust Date**: *Subtract 1 day* from *Date*. Then another **Adjust Date**: *Get Start of Day* of that
   result. Rename the variable (tap it → Rename) to `Od` (start of yesterday).
3. **Format Date**: *Date* (current), format *Custom* `yyyy-MM-dd` → rename to `Dnes`.
   **Format Date**: the date from step 2's first Adjust Date, *Custom* `yyyy-MM-dd` → rename to `Vcera`.
4. **Find Health Samples**:
   - *Type* is **Steps**;
   - *Start Date* **is after** `Od`;
   - optional, if other apps write steps into Apple Health: *Source* is your iPhone;
   - *Sort by* Start Date, **Limit off**, *Group by* **None**. Grouping into hours would smear steps across
     the hour and break the 15-minute merge with the watch.
5. **If** *Health Samples* → *Count* **is** `0`: **Stop This Shortcut**. **End If**. (This is the guard.)
6. **Repeat with Each** item in *Health Samples*:
   1. **Format Date**: *Repeat Item* → *Start Date*, format **ISO 8601**, *Include ISO 8601 Time* on.
   2. **Format Date**: *Repeat Item* → *End Date*, same format.
   3. **Dictionary** with three keys:
      - `start`: Text, the first formatted date;
      - `end`: Text, the second formatted date;
      - `count`: **Number**, *Repeat Item* → *Value*. Use the Number type, not Text: Czech number formatting
        (`1 234`) is not valid JSON.
   4. **Add to Variable** `Kroky`.
7. **End Repeat**.
8. **Dictionary**: key `source`, Text `apple_health`. Then **Set Dictionary Value**: key `days`, value an
   **Array** with the items `Vcera` and `Dnes`. Then **Set Dictionary Value**: key `steps`, value `Kroky`.
9. **Get Contents of URL**:
   - URL `https://biggyserver.tailfff1d3.ts.net/api/webhooks/health`;
   - *Method* POST;
   - *Headers*: `X-Webhook-Token` = the token (the server reads the JSON whatever `Content-Type` Shortcuts sends);
   - *Request Body* **File**, the dictionary from step 8.
10. **Show Result** (keep it while testing; remove it once automations run, or they show a banner).

## Test

Run it by hand. A good reply lists both days:

```json
[{"date":"2026-10-16","steps":9312,"steps_method":"single_source","sleep_hours":null},
 {"date":"2026-10-17","steps":4120,"steps_method":"single_source","sleep_hours":null}]
```

Compare today's number with the Health app (Steps → *Show All Data* → this iPhone). **Nastavení → Zdroje kroků a
spánku** now shows *iPhone (Zkratky)* with the time of the run.

| Reply | Meaning |
|---|---|
| `401 Invalid webhook token` | Token header missing or mistyped. |
| `503 Webhooks disabled` | `WEBHOOK_TOKEN` is not set on the server. |
| `422` with `detail` | The JSON shape is off. `detail` names the field: typically a date without a time zone offset (ISO 8601 option), or `count` sent as Text. |
| Timeout / could not connect | Tailscale is off on the phone. |

## Automations

In **Shortcuts → Automation → +**, create each of these, set to **Run Immediately** with **Notify When Run**
off, and with the action **Run Shortcut → Fitness Hub kroky**:

- **Time of Day** at 12:00, 18:00 and 23:30, daily. These succeed when the phone happens to be unlocked.
- **App** → *Is Opened* → an app you open several times a day (for example your messenger). This runs while
  the phone is unlocked, so it reliably reads Health.

Every run costs a few seconds in the background and is harmless to repeat.

## Later

The Life Dashboard Companion iOS app speaks the format `/api/webhooks/health-connect` already accepts
(`source: healthkit_ios`). Once it is on TestFlight or the App Store it can replace this Shortcut (backlog).
