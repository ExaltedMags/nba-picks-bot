import os

# Channel IDs — update these after running the setup instructions in README.md
# EV     = Guy Boston Sports (@GuyBostonSports)
# FULL90 = thefull90 (@thefull90) — FIFA World Cup picks
# Channel IDs are public (not secrets), so FULL90 defaults to the real ID and
# only needs an env override if the channel ever changes.
# Use `or` rather than get()'s default so an env var that is *set but empty* —
# e.g. the workflow passing ${{ secrets.FULL90_CHANNEL_ID }} when that secret
# isn't defined, which GitHub injects as "" — falls back to the default instead
# of overriding it with an empty string (which yields an empty playlistId → 400).
EV_CHANNEL_ID = os.environ.get("EV_CHANNEL_ID") or "UCxxxxxxxxxxxxxxxxxxxxxxxxxx"
FULL90_CHANNEL_ID = os.environ.get("FULL90_CHANNEL_ID") or "UCbcQP0aVkJp1SqBn0uYJpmw"

# API credentials from environment
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
SUPADATA_API_KEY = os.environ.get("SUPADATA_API_KEY")

# Email delivery
GMAIL_SENDER = os.environ.get("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
REPORT_RECIPIENT = os.environ.get("REPORT_RECIPIENT")

# HTTP proxy URL for scraping — paste full URL from your proxy provider dashboard
# Format: http://username:password@host:port
# e.g. Webshare: copy the proxy URL directly from https://proxy.webshare.io/proxy/list
HTTP_PROXY_URL = os.environ.get("HTTP_PROXY_URL")

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# Freshness window: a video only counts as "today's" if it was published within
# this many hours of the run. This prevents grabbing a previous day's video and
# presenting it as today's. Tuned for the daily 16:00 UTC schedule (today's
# picks post in the ~16h before the run; the prior day's are ~24h+ old, so 22h
# accepts today's and rejects yesterday's). Adjust if you change the cron time.
MAX_VIDEO_AGE_HOURS = int(os.environ.get("MAX_VIDEO_AGE_HOURS", "22"))

# Timezone
PHT = "Asia/Manila"

# WNBA team keywords for the picks filter
WNBA_TEAM_NAMES = [
    "Aces", "Liberty", "Sky", "Sun", "Fever", "Mystics", "Dream",
    "Lynx", "Mercury", "Storm", "Sparks", "Wings", "Valkyries",
]

# Sports to exclude from the WNBA filter (matched on whole words, so "NBA"
# excludes men's NBA without catching "WNBA").
EXCLUDE_SPORTS = ["NBA", "NFL", "MLB", "CFB", "NCAAB", "NCAAF", "Soccer", "NHL", "Tennis", "UFC"]

# Domains that indicate a valid picks article link in Ev's pinned comment
EV_PICKS_DOMAINS = ["guybostonsports.com"]
