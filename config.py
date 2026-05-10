import os

# Channel IDs — update these after running the setup instructions in README.md
EV_CHANNEL_ID = os.environ.get("EV_CHANNEL_ID", "UCxxxxxxxxxxxxxxxxxxxxxxxxxx")
DAFT_CHANNEL_ID = os.environ.get("DAFT_CHANNEL_ID", "UCxxxxxxxxxxxxxxxxxxxxxxxxxx")

# API credentials from environment
YOUTUBE_API_KEY = os.environ.get("YOUTUBE_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Email delivery
GMAIL_SENDER = os.environ.get("GMAIL_SENDER")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD")
REPORT_RECIPIENT = os.environ.get("REPORT_RECIPIENT")

# Webshare proxy — required for transcript fetching on GitHub Actions
# Free tier at https://www.webshare.io (10 proxies, no cost)
# Leave unset to skip proxy (transcripts will fail on cloud runners)
WEBSHARE_PROXY_USERNAME = os.environ.get("WEBSHARE_PROXY_USERNAME")
WEBSHARE_PROXY_PASSWORD = os.environ.get("WEBSHARE_PROXY_PASSWORD")

# Gemini model
GEMINI_MODEL = "gemini-2.5-flash"

# Timezone
PHT = "Asia/Manila"

# NBA team keywords for Ev's channel filter
NBA_TEAM_NAMES = [
    "Cavs", "Cavaliers", "Lakers", "Celtics", "Warriors", "Knicks",
    "Nets", "Bulls", "Heat", "Bucks", "76ers", "Sixers", "Suns",
    "Nuggets", "Clippers", "Mavericks", "Mavs", "Grizzlies", "Pelicans",
    "Thunder", "Jazz", "Timberwolves", "Wolves", "Rockets", "Spurs",
    "Kings", "Blazers", "Hornets", "Hawks", "Magic", "Pacers", "Pistons",
    "Raptors", "Wizards",
]

# Sports to exclude for Ev's NBA filter
EXCLUDE_SPORTS = ["NFL", "MLB", "CFB", "NCAAB", "Soccer", "NHL", "Tennis", "WNBA"]

# Domains that indicate a valid picks article link in Ev's pinned comment
EV_PICKS_DOMAINS = ["guybostonsports.com"]
