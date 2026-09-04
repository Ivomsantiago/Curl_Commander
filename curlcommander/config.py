from pathlib import Path

APP_DIR = Path.home() / ".curlcommander"
DB_PATH = APP_DIR / "history.db"
HISTORY_LIMIT = 30
DEFAULT_TIMEOUT = 30.0
# Max response body rendered to the terminal before truncation (bytes).
# --output always saves the full content regardless of this limit.
DISPLAY_LIMIT_BYTES = 1_000_000
DEFAULT_METHOD = "GET"
HTTP_METHODS = ["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"]
AUTH_TYPES = ["none", "bearer", "basic", "apikey"]
BODY_TYPES = ["none", "json", "form", "raw"]
