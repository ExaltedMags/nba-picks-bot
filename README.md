# WNBA Picks Bot

Automated daily WNBA picks report emailed at 12:00 AM Philippine Time.

Fetches the latest WNBA picks videos from **Guy Boston Sports (`@GuyBostonSports`)** and **Do Your Job Sports (`@DoYourJobSports`)**, extracts transcripts, scrapes pinned comment pick sheets, summarizes via Gemini, and sends a consolidated report.

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
- For `@DoYourJobSports`: visit `https://www.youtube.com/@DoYourJobSports`

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
| `EV_CHANNEL_ID` | Guy Boston Sports channel ID (from step 4) |
| `DYJ_CHANNEL_ID` | Do Your Job Sports channel ID (from step 4) |
| `HTTP_PROXY_URL` | Optional proxy URL for scraping |

### 6. Test the workflow
Go to **Actions** tab → **WNBA Picks Daily Report** → **Run workflow**

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
export EV_CHANNEL_ID=...
export DYJ_CHANNEL_ID=...

python main.py
```

---

## Project Structure

```
nba-picks-bot/
├── .github/workflows/nba_picks.yml   # GitHub Actions cron
├── main.py                            # Orchestrator
├── fetch_video.py                     # YouTube Data API: latest video per channel
├── get_transcript.py                  # Supadata transcript extraction + cleaning
├── get_pinned_comment.py              # YouTube API: pinned comment URL extraction
├── scrape_picks.py                    # Jina Reader article scraper
├── summarize.py                       # Gemini API call + prompt
├── send_email.py                      # Gmail SMTP delivery
├── config.py                          # Channel IDs, team names, filter logic
└── requirements.txt
```

---

## Schedule

Runs daily at **4:00 PM UTC = 12:00 AM Philippine Time (PHT)**.

---

## Reliability / Guardrails

The email is sent **only when both channels are OK** — you never get a
misleading, partial, or stale report.

- Each channel is classified **OK** (clean summary), **EMPTY** (no fresh video),
  or **DEGRADED** (a video existed but couldn't be turned into a usable
  summary — e.g. the AI fell back to a raw transcript excerpt, or no
  transcript/picks sheet could be retrieved).
- A **DEGRADED** channel triggers a full pipeline re-run (up to 3 attempts with
  backoff).
- If, after retries, **either channel is not OK**, the email is **blocked
  entirely**:
  - **DEGRADED** (something broke) → job exits non-zero, so the GitHub Actions
    run goes **red** and you're alerted. Enable Actions failure notifications.
  - **EMPTY** (off-day or today's video not posted yet) → job exits zero (no
    email, but not a failure — there was simply nothing to report).

### Freshness (no stale videos)

A video only counts as "today's" if it was published within
`MAX_VIDEO_AGE_HOURS` (default **22h**, env-configurable). If today's video
isn't up yet, the channel is treated as **EMPTY** rather than silently falling
back to the previous day's video and mislabeling it as today's. The 22h default
is tuned to the 16:00 UTC schedule — adjust it if you change the cron time.
