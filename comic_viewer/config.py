from pathlib import Path

APP_NAME = "CBRReaderPy"
DEFAULT_LIBRARY = Path.home() / "CBRLibrary"
APP_SUPPORT = Path.home() / "Library" / "Application Support" / APP_NAME
STATE_FILE = APP_SUPPORT / "state.json"
MSAL_CACHE_FILE = APP_SUPPORT / "msal_cache.bin"

GDRIVE_CREDENTIALS_FILE = APP_SUPPORT / "gdrive_credentials.json"  # JSON do OAuth Client (Desktop)
GDRIVE_TOKEN_FILE = APP_SUPPORT / "gdrive_token.json"              # token salvo após login
GDRIVE_SCOPES = ["https://www.googleapis.com/auth/drive.readonly"] # só leitura

# Microsoft Entra / Azure AD
# Coloque seu Client ID abaixo:
CLIENT_ID = "YOUR_CLIENT_ID_HERE"  # <<< SUBSTITUA

AUTHORITIES = [
    "https://login.microsoftonline.com/common",
    "https://login.microsoftonline.com/consumers",
    "https://login.microsoftonline.com/organizations",
]

SCOPES = [
    "https://graph.microsoft.com/User.Read",
    "https://graph.microsoft.com/Files.Read",
]

def ensure_dirs():
    APP_SUPPORT.mkdir(parents=True, exist_ok=True)
    DEFAULT_LIBRARY.mkdir(parents=True, exist_ok=True)
