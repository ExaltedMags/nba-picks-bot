# NBA Picks Bot

Automated daily NBA picks report emailed at 10:00 PM Philippine Time
(never later than 1:00 AM PHT, never in the middle of the night).

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

### 6. Test the workflow
Go to **Actions** tab → **NBA Picks Daily Report** → **Run workflow**. Tick
**force** to run right away. Without it, the run follows the normal schedule
rules below, so outside the evening it just logs why it skipped.

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
├── schedule_guard.py                  # Decides skip / wait-until-22:00 / run
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

**Target:** one email per night at **10:00 PM PHT**. If that slot is missed, a
run starts by 1:00 AM PHT at the latest. Nothing to set up outside GitHub.

### Why the old schedule was late

GitHub Actions cron is best-effort. For this repo, the `0 14 * * *`
(10:00 PM PHT) schedule started between **01:11 and 06:35 AM PHT** on every
scheduled run from Oct 24 to Nov 5, 2026: 3 to 8½ hours late. GitHub doesn't
guarantee start times, so asking for 10 PM can't make it start at 10 PM.

### How it works now: arrive early, wait on the runner

Instead of asking GitHub to *start* at 10 PM, the workflow asks it to start
several times through the afternoon. The first run that shows up early holds
until 10 PM itself. The runner keeps the clock, so GitHub's delay doesn't
matter.

Scheduled runs: **12:07, 14:07, 16:07, 18:07, 20:07 PHT** (`7 4,6,8,10,12 * * *` UTC).
Each run goes through `schedule_guard.py`:

| When the run actually starts (PHT) | What it does |
|---|---|
| before 18:00 | Skips in seconds. A later scheduled run will cover tonight. |
| 18:00 – 22:00 | **Waits on the runner until 22:00**, then runs. |
| 22:00 – 01:00 | Runs immediately. |
| after 01:00 | Skips. No more 3–4 AM emails. |

Replaying the real delays from Oct 24 – Nov 5 (3.2h to 8.6h) through this
schedule, **every night sends at exactly 22:00**. At least one of the five
triggers lands in the 18:00–01:00 range whether GitHub is on time or up to
~9h late.

**Safety rails**

- **One email per night.** After a run sends, it stores a marker in the
  Actions cache under tonight's date. Every later run that night sees it and
  stops. Runs after midnight count as the previous evening.
- **One sender at a time.** The send job uses a `concurrency` group. A
  second eligible run waits behind the first, then sees the marker and exits.
  If several runs pile up, GitHub cancels the extra queued ones. Grey
  "cancelled" runs in the Actions tab are expected and harmless.
- **Retries for late videos.** If nothing was emailed (no fresh videos yet, or
  a source broke), the run retries every 30 min until 23:30 PHT.
- **Free.** The repo is public, so Actions minutes, including the waiting,
  cost nothing. If you make the repo **private**, the waiting will use your
  2,000 free minutes/month, so lower `MAX_EARLY_WAIT_MIN` or go back to an
  external trigger.

**Settings** (optional repository *variables*: Settings → Secrets and
variables → Actions → Variables):

| Variable | Default | Meaning |
|---|---|---|
| `SEND_WINDOW_START` | `22:00` | Target send time (PHT) |
| `SEND_WINDOW_END` | `01:00` | No run starts after this (PHT) |
| `RETRY_UNTIL` | `23:30` | Last retry when nothing was sent (PHT) |
| `MAX_EARLY_WAIT_MIN` | `240` | Longest an early run will wait. Keep it ≤ 240 so wait + retries fit GitHub's 6h job limit |

### Keeping it alive

GitHub turns off scheduled workflows in public repos after **60 days with no
commits**. You'll get an email, and the Actions tab shows a banner. Click
*Enable workflow* (or push any commit) to turn it back on.

### External pingers (optional)

The workflow still accepts `workflow_dispatch`. If you later want a second,
independent trigger (e.g. cron-job.org or a Cloudflare Worker calling
`POST /repos/ExaltedMags/nba-picks-bot/actions/workflows/nba_picks.yml/dispatches`
with `{"ref":"main"}` and a token that has *Actions: write*), it plugs in with
no changes. The guard and once-per-night marker apply to it too. It isn't
needed.

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
is tuned to the 22:00–01:00 PHT send window. Adjust it if you move the window.
