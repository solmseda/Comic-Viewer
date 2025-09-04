from __future__ import annotations
from pathlib import Path
from typing import Optional
import json

from PyQt5.QtWidgets import QWidget, QMessageBox

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

from ..config import GDRIVE_SCOPES, GDRIVE_CREDENTIALS_FILE, GDRIVE_TOKEN_FILE

def ensure_dirs():
    GDRIVE_TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)

def load_credentials_silent() -> Optional[Credentials]:
    ensure_dirs()
    if GDRIVE_TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(GDRIVE_TOKEN_FILE), GDRIVE_SCOPES)
        if creds and creds.valid:
            return creds
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
                save_credentials(creds)
                return creds
            except Exception:
                return None
    return None

def save_credentials(creds: Credentials) -> None:
    ensure_dirs()
    GDRIVE_TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")

def interactive_login(parent: QWidget) -> Optional[Credentials]:
    ensure_dirs()
    if not GDRIVE_CREDENTIALS_FILE.exists():
        QMessageBox.critical(parent, "Google Drive",
            f"Arquivo de credenciais não encontrado:\n{GDRIVE_CREDENTIALS_FILE}\n\n"
            "Baixe o JSON de cliente OAuth (Aplicativo para computador) e salve nesse caminho.")
        return None
    try:
        flow = InstalledAppFlow.from_client_secrets_file(str(GDRIVE_CREDENTIALS_FILE), GDRIVE_SCOPES)
        # abre navegador local; cai para console se necessário
        creds = flow.run_local_server(port=0)
        save_credentials(creds)
        return creds
    except Exception as e:
        QMessageBox.critical(parent, "Google Drive", f"Falha ao autenticar: {e}")
        return None
