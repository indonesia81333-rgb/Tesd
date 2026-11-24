import os

API_ID = int(os.environ.get("API_ID", "0"))
API_HASH = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")

# Gofile: leave empty to use an anonymous guest account (files may expire).
GOFILE_API_KEY = os.environ.get("GOFILE_API_KEY", "")
# Gofile website token used by their content API. It changes occasionally,
# so it is configurable instead of hardcoded in the code.
GOFILE_WT = os.environ.get("GOFILE_WT", "4fd6sg89d7s6")

# Comma separated Telegram user IDs allowed to use the bot. Empty = everyone.
ALLOWED_USERS = {
    int(x) for x in os.environ.get("ALLOWED_USERS", "").split(",") if x.strip()
}

PORT = int(os.environ.get("PORT", "10000"))  # Render provides PORT
MAX_FILE_SIZE = int(os.environ.get("MAX_FILE_SIZE_GB", "4")) * 1024**3
MAX_PARALLEL = int(os.environ.get("MAX_PARALLEL", "2"))
DOWNLOAD_DIR = os.environ.get("DOWNLOAD_DIR", "downloads")
