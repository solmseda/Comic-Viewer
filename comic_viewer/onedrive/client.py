from typing import Optional, Dict, List
import requests
import msal
from PyQt5.QtWidgets import QWidget, QMessageBox
from ..config import CLIENT_ID, SCOPES, AUTHORITIES, MSAL_CACHE_FILE
from ..state import save_state
from .auth import TokenCache, try_authorities

class OneDriveClient:
    def __init__(self, state: dict):
        self.state = state
        self.cache = TokenCache(MSAL_CACHE_FILE)
        auth = self.state["onedrive"].get("authority") or AUTHORITIES[0]
        self.app = msal.PublicClientApplication(client_id=CLIENT_ID, authority=auth, token_cache=self.cache.cache)

    def _reinit(self, authority: str):
        self.state["onedrive"]["authority"] = authority
        save_state(self.state)
        self.app = msal.PublicClientApplication(client_id=self.app.client_id, authority=authority, token_cache=self.cache.cache)

    def _get_token_silent(self) -> Optional[Dict]:
        accounts = self.app.get_accounts()
        if accounts:
            tok = self.app.acquire_token_silent(SCOPES, account=accounts[0])
            if tok and "access_token" in tok:
                return tok
        return None

    def ensure_token(self, parent: QWidget) -> Optional[Dict]:
        tok = self._get_token_silent()
        if tok: return tok

        # tenta device code (common/consumers/organizations)
        def mk_app(authority: str):
            self._reinit(authority)
            return self.app
        return try_authorities(parent, mk_app, self.state)

    def sign_out(self):
        for acc in self.app.get_accounts():
            self.app.remove_account(acc)
        self.cache.persist()

    def _auth_headers(self, token: Dict) -> Dict[str, str]:
        return {"Authorization": f"Bearer {token['access_token']}"}

    def get_profile_label(self, token: Dict) -> str:
        try:
            r = requests.get("https://graph.microsoft.com/v1.0/me?$select=displayName,mail,userPrincipalName",
                             headers=self._auth_headers(token), timeout=15)
            if r.ok:
                me = r.json()
                mail = me.get("mail") or me.get("userPrincipalName") or "conta Microsoft"
                return f"{me.get('displayName') or ''} <{mail}>".strip()
        except Exception:
            pass
        return "Conectado"

    # navegação
    def list_children(self, token: Dict, folder_id: Optional[str]) -> List[Dict]:
        if folder_id:
            url = f"https://graph.microsoft.com/v1.0/me/drive/items/{folder_id}/children?$select=id,name,folder,size"
        else:
            url = "https://graph.microsoft.com/v1.0/me/drive/root/children?$select=id,name,folder,size"
        resp = requests.get(url, headers=self._auth_headers(token), timeout=30)
        resp.raise_for_status()
        return resp.json().get("value", [])

    def iter_cbr_files(self, token: Dict, folder_id: str, recursive: bool = True):
        stack = [folder_id]
        while stack:
            fid = stack.pop()
            for item in self.list_children(token, fid):
                if item.get("folder"):
                    if recursive: stack.append(item["id"])
                else:
                    name = item["name"].lower()
                    if name.endswith(".cbr") or name.endswith(".cbz"):
                        yield item

    def download_file(self, token: Dict, item_id: str) -> bytes:
        url = f"https://graph.microsoft.com/v1.0/me/drive/items/{item_id}/content"
        r = requests.get(url, headers=self._auth_headers(token), timeout=180, allow_redirects=True)
        r.raise_for_status()
        return r.content
