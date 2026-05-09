# NBA Picks Bot

Automated daily NBA picks report delivered to Telegram at 12:00 AM Philippine Time.

Fetches the latest picks videos from **GuyBostonSports (Ev)** and **DaftPreviews (Daft)**, extracts transcripts, scrapes pinned comment pick sheets, summarizes via Gemini, and sends a consolidated report.

---

## Setup Checklist

### 1. Get YouTube Data API Key
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create/select a project → enable **YouTube Data API v3**
3. Credentials → **API Key** → copy it

### 2. Get Gemini API Key
1. Go to [Google AI Studio](https://aistudio.google.com/)
2. **Get API Key** → Create API Key → copy it

### 3. Create Telegram Bot
1. Open Telegram → message **@BotFather** → `/newbot`
2. Copy the bot token
3. Start a chat with your bot (send any message)
4. Visit `https://api.telegram.org/bot{YOUR_TOKEN}/getUpdates` → find your `chat.id`

### 4. Find Channel IDs
YouTube channel IDs are not always in the URL. To find them:
- Go to the channel page → view page source (Ctrl+U) → search for `"channelId"` or `"externalId"`
- For `@GuyBostonSports`: visit `https://www.youtube.com/@GuyBostonSports`
- For `@daftpreviews`: visit `https://www.youtube.com/@daftpreviews`

### 5. Add GitHub Secrets
Push this repo to GitHub, then go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `YOUTUBE_API_KEY` | From step 1 |
| `GEMINI_API_KEY` | From step 2 |
| `TELEGRAM_BOT_TOKEN` | From step 3 |
| `TELEGRAM_CHAT_ID` | From step 3 |
| `EV_CHANNEL_ID` | From step 4 |
| `DAFT_CHANNEL_ID` | From step 4 |

### 6. Test the workflow
Go to **Actions** tab → **NBA Picks Daily Report** → **Run workflow**

---

## Local Testing

```bash
pip install -r requirements.txt

export YOUTUBE_API_KEY=...
export GEMINI_API_KEY=...
export TELEGRAM_BOT_TOKEN=...
export TELEGRAM_CHAT_ID=...
export EV_CHANNEL_ID=...
export DAFT_CHANNEL_ID=...

python main.py
```

---

## Project Structure

```
nba-picks-bot/
├── .github/workflows/nba_picks.yml   # GitHub Actions cron
├── main.py                            # Orchestrator
├── fetch_video.py                     # YouTube Data API: latest video per channel
├── get_transcript.py                  # yt-dlp caption extraction + cleaning
├── get_pinned_comment.py              # YouTube API: pinned comment URL extraction
├── scrape_picks.py                    # BeautifulSoup article scraper
├── summarize.py                       # Gemini API call + prompt
├── send_telegram.py                   # Telegram Bot delivery
├── config.py                          # Channel IDs, team names, filter logic
└── requirements.txt
```

---

## Schedule

Runs daily at **4:00 PM UTC = 12:00 AM Philippine Time (PHT)**.
