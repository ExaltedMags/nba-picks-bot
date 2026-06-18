import os

# Channel IDs — update these after running the setup instructions in README.md
# EV  = Guy Boston Sports (@GuyBostonSports)
# DYJ = Do Your Job Sports (@DoYourJobSports)
EV_CHANNEL_ID = os.environ.get("EV_CHANNEL_ID", "UCxxxxxxxxxxxxxxxxxxxxxxxxxx")
DYJ_CHANNEL_ID = os.environ.get("DYJ_CHANNEL_ID", "UCxxxxxxxxxxxxxxxxxxxxxxxxxx")

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
