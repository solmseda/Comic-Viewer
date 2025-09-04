from __future__ import annotations
from typing import Dict, Iterable, Optional, List
from PyQt5.QtWidgets import QWidget
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from .auth import load_credentials_silent, interactive_login, save_credentials
from ..config import GDRIVE_SCOPES

class GDriveClient:
    def __init__(self, state: dict):
        self.state = state
        self.creds = load_credentials_silent()

    def ensure_creds(self, parent: QWidget):
        if self.creds:
            return self.creds
        self.creds = interactive_login(parent)
        return self.creds

    def _service(self):
        return build("drive", "v3", credentials=self.creds, cache_discovery=False)

    def account_label(self) -> str:
        try:
            svc = self._service()
            about = svc.about().get(fields="user(displayName,emailAddress)").execute()
            u = about.get("user", {})
            name = u.get("displayName") or ""
            email = u.get("emailAddress") or ""
            return f"{name} <{email}>".strip()
        except Exception:
            return "Conectado"

    # pasta raiz e filhos
    def list_children(self, folder_id: Optional[str]) -> List[Dict]:
        svc = self._service()
        # Monta a query base
        parent = "root" if folder_id in (None, "root") else folder_id
        q = f"'{parent}' in parents and trashed=false"
        fields = "nextPageToken, files(id,name,mimeType,size,driveId)"
        page_token = None
        out: List[Dict] = []
        while True:
            resp = svc.files().list(
                q=q,
                fields=fields,
                pageToken=page_token,
                pageSize=200,
                includeItemsFromAllDrives=True,  # <<< importante
                supportsAllDrives=True  # <<< importante
            ).execute()
            out.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break
        # pastas primeiro, depois por nome
        out.sort(key=lambda f: (f["mimeType"] != "application/vnd.google-apps.folder", f["name"].lower()))
        return out

    def iter_cbr_files(self, folder_id: str, recursive: bool = True) -> Iterable[Dict]:
        stack = [folder_id or "root"]
        svc = self._service()
        while stack:
            fid = stack.pop()
            for f in self.list_children(fid):
                if f["mimeType"] == "application/vnd.google-apps.folder":
                    if recursive: stack.append(f["id"])
                else:
                    name = f["name"].lower()
                    if name.endswith(".cbr") or name.endswith(".cbz"):
                        yield f

    def download_file(self, file_id: str) -> bytes:
        svc = self._service()
        # arquivos binários “normais” usam files().get_media; Google Docs precisam export, mas .cbr/.cbz são binários
        from googleapiclient.http import MediaIoBaseDownload
        import io
        req = svc.files().get_media(fileId=file_id)
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, req, chunksize=1024*1024)
        done = False
        while not done:
            status, done = downloader.next_chunk()
        return fh.getvalue()
