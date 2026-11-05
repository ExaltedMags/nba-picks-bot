# NBA Picks Bot

Automated daily NBA picks report emailed around 10:00 PM Philippine Time
(always inside 9:30 PM – 1:00 AM PHT, never in the middle of the night).

Fetches the latest picks videos, extracts transcripts, scrapes pinned comment
pick sheets, summarizes via Gemini, and sends a consolidated report.

Sources:

| Source | Channel | Content |
|---|---|---|
| EV | Guy Boston Sports (`@GuyBostonSports`) | NBA picks (video + guybostonsports.com sheet) |
| DAFT | Daft Previews (`@daftpreviews`) | NBA best bets / player props (video only) |

Every source is **additive**: it's included when a fresh video exists and
silently dropped otherwise (e.g. an off-day). The email is sent
whenever at least one source has clean content (see Guardrails).

---

## Setup Checklist

### 1. Get YouTube Data API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select a project → enable **YouTube Data API v3**
3. Credentials → **API Key** → copy it

### 2. Get Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. **Get API Key** → Create API Key → copy it

### 3. Set up Gmail delivery
1. Use a Gmail account as the sender (`GMAIL_SENDER`)
2. Enable 2-Step Verification, then create an **App Password** → use it as `GMAIL_APP_PASSWORD`
3. Set `REPORT_RECIPIENT` to the address that should receive the report

### 4. Find Channel IDs
YouTube channel IDs are not always in the URL. To find them:
- Go to the channel page → view page source (Ctrl+U) → search for `"channelId"` or `"externalId"` (a `UC…` string)
- For `@GuyBostonSports`: visit `https://www.youtube.com/@GuyBostonSports`
- Both channel IDs are wired in as defaults; only set `EV_CHANNEL_ID` /
  `DAFT_CHANNEL_ID` if you need to override them.

### 5. Add GitHub Secrets
Push this repo to GitHub, then go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `YOUTUBE_API_KEY` | From step 1 |
| `GEMINI_API_KEY` | From step 2 |
| `SUPADATA_API_KEY` | Transcript API key |
| `GMAIL_SENDER` | Gmail address that sends the report |
| `GMAIL_APP_PASSWORD` | Gmail app password |
| `REPORT_RECIPIENT` | Email address to receive the report |
| `EV_CHANNEL_ID` | Optional — overrides the built-in Guy Boston Sports channel ID |
| `DAFT_CHANNEL_ID` | Optional — overrides the built-in Daft Previews channel ID |
| `HTTP_PROXY_URL` | Optional proxy URL for scraping |

### 6. Set up the on-time trigger
Follow [Schedule → Setup](#setup-cron-joborg) below. Without it the bot only
has GitHub's own scheduler, which is regularly hours late.

### 7. Test the workflow
Go to **Actions** tab → **NBA Picks Daily Report** → **Run workflow**. Tick
**force** to run outside the evening window (otherwise the run just logs
"outside the send window" and exits).

---

## Local Testing

```bash
pip install -r requirements.txt

export YOUTUBE_API_KEY=...
export GEMINI_API_KEY=...
export SUPADATA_API_KEY=...
export GMAIL_SENDER=...
export GMAIL_APP_PASSWORD=...
export REPORT_RECIPIENT=...
# export EV_CHANNEL_ID=...     # optional
# export DAFT_CHANNEL_ID=...   # optional

python main.py
```

---

## Project Structure

```
nba-picks-bot/
├── .github/workflows/nba_picks.yml   # GitHub Actions cron
├── main.py                            # Orchestrator
├── schedule_guard.py                  # Send-window + once-per-night check
├── fetch_video.py                     # YouTube Data API: latest video per channel
├── get_transcript.py                  # Supadata transcript extraction + cleaning
├── get_pinned_comment.py              # YouTube API: pinned comment URL extraction
├── scrape_picks.py                    # Jina Reader article scraper
├── summarize.py                       # Gemini API call (structured JSON picks)
├── render_report.py                   # Email rendering: HTML + plain-text bodies
├── send_email.py                      # Gmail SMTP delivery (multipart: HTML + text)
├── config.py                          # Channel IDs, team names, filter logic
└── requirements.txt
```

---

## Schedule

**Target:** one email per night, sent at ~10:00 PM PHT, never outside the
**21:30–01:00 PHT send window**.

### Why GitHub's `schedule` alone isn't enough

GitHub Actions cron is best-effort. For this repo, the `0 14 * * *`
(10:00 PM PHT) schedule started between **01:11 and 06:35 AM PHT** on every
scheduled run from Oct 24 to Nov 5, 2026: 3 to 8½ hours late. GitHub doesn't
guarantee start times, and runs set for the top of the hour wait the longest.

### How it works now

| Trigger | When | Role |
|---|---|---|
| **cron-job.org → `workflow_dispatch` API** | 22:00, 22:30, 23:00, 23:30 PHT | **Primary.** Starts within seconds. |
| GitHub `schedule` | 22:17, 22:47 PHT (often hours late) | Backup. If it fires late, it does nothing. |
| Manual **Run workflow** | any time | Testing (tick **force**). |

Every run first runs `schedule_guard.py`:

1. **Send window.** If it isn't 21:30–01:00 PHT, the run exits in a few
   seconds without doing anything. That means a GitHub run that turns up at
   4 AM can't email you.
2. **Once per night.** After a run emails the report, it saves a marker
   in the Actions cache under tonight's date. Later runs that night find it
   and skip. Runs after midnight still count as the previous evening.
3. **Built-in retries.** A run that finds no fresh videos yet, or fails,
   doesn't write the marker, so the 22:30 / 23:00 / 23:30 runs try again. That
   catches late uploads too.

A `concurrency` group makes sure two triggers that arrive together run one
after the other.

You can change the window with repository **variables** (Settings → Secrets
and variables → Actions → Variables): `SEND_WINDOW_START` / `SEND_WINDOW_END`,
as `HH:MM` PHT.

### Setup (cron-job.org)

cron-job.org is free and runs each job within seconds of its time. It also
supports the Asia/Manila time zone and emails you when a job fails.

**1. Create a GitHub token that can start the workflow**

- GitHub → Settings → Developer settings → **Fine-grained personal access
  tokens** → *Generate new token*
- Repository access: **Only select repositories** → `nba-picks-bot`
- Permissions → Repository permissions → **Actions: Read and write**
  (nothing else is needed)
- Expiration: the longest option you're offered. **Put the expiry date in your
  calendar.** If the token expires, the trigger quietly stops working.

**2. Create the cron job** at <https://console.cron-job.org> → *Create cronjob*

- **URL:** `https://api.github.com/repos/ExaltedMags/nba-picks-bot/actions/workflows/nba_picks.yml/dispatches`
- **Schedule:** *Custom* → Days of month: every, Days of week: every,
  Months: every, **Hours: 22, 23**, **Minutes: 0, 30**
- **Time zone:** `Asia/Manila`
- **Advanced** tab:
  - Request method: **POST**
  - Headers:
    - `Accept: application/vnd.github+json`
    - `Authorization: Bearer <your token>`
    - `X-GitHub-Api-Version: 2022-11-28`
    - `Content-Type: application/json`
  - Request body: `{"ref":"main"}`
- **Notifications:** turn on *notify on failure* and *notify when the job is
  disabled*.

**3. Test it:** use *Test run* in cron-job.org. A good response is
**`204 No Content`**, and a new "workflow_dispatch" run should appear in the
Actions tab right away. It will log "outside the send window" unless you test
between 21:30 and 01:00 PHT. That's expected.

| Response | Meaning |
|---|---|
| `401` | Token is wrong or expired |
| `403` / `404` | Token can't access this repo, or doesn't have Actions write |
| `422` | Wrong branch in `ref`, or a typo in the workflow file name |

### Keeping the backup alive

GitHub turns off scheduled workflows in public repos after 60 days with no
commits. The cron-job.org trigger is **not** affected by this. If the Actions
tab shows a "scheduled workflow disabled" banner, just re-enable it.

---

## Reliability / Guardrails

The email is sent whenever **at least one source has clean content** — you get
the good picks even if another channel didn't post, but you never see broken or
stale content.

- Each source is classified **OK** (clean summary), **EMPTY** (no fresh video),
  or **DEGRADED** (a video existed but couldn't be turned into a usable
  summary — e.g. the AI fell back to a raw transcript excerpt, or no
  transcript/picks sheet could be retrieved).
- A **DEGRADED** source triggers a full pipeline re-run (up to 3 attempts with
  backoff).
- After retries, each source is handled uniformly:
  - **OK** → shown in the report.
  - **EMPTY** / **DEGRADED** → omitted and listed transparently under
    "Not included today", so you always know what was checked.
- The email is only **skipped** when *no* source is OK:
  - all **EMPTY** (true off-day) → exit 0 (clean no-op, no email).
  - at least one **DEGRADED** and none OK → exit non-zero, so the GitHub Actions
    run goes **red** and you're alerted. Enable Actions failure notifications.

### Freshness (no stale videos)

A video only counts as "today's" if it was published within
`MAX_VIDEO_AGE_HOURS` (default **22h**, env-configurable). If today's video
isn't up yet, the channel is treated as **EMPTY** rather than silently falling
back to the previous day's video and mislabeling it as today's. The 22h default
is tuned to the 21:30–01:00 PHT send window. Adjust it if you move the window.
