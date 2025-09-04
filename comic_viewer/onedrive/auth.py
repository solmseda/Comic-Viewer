from pathlib import Path
from typing import List, Optional, Dict
import msal
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QLabel, QDialogButtonBox, QMessageBox, QWidget, QProgressBar
import webbrowser
from PyQt5.QtCore import QThread, pyqtSignal
from ..config import MSAL_CACHE_FILE, SCOPES, AUTHORITIES
from ..state import save_state

class TokenCache:
    def __init__(self, path: Path):
        self.path = path
        self.cache = msal.SerializableTokenCache()
        self._load()
    def _load(self):
        if self.path.exists():
            try:
                self.cache.deserialize(self.path.read_text())
            except Exception:
                pass
    def persist(self):
        if self.cache.has_state_changed:
            self.path.write_text(self.cache.serialize())

class MSALDeviceCodeThread(QThread):
    result = pyqtSignal(object, object)  # (token, error)
    def __init__(self, app: msal.PublicClientApplication, scopes: List[str]):
        super().__init__()
        self.app = app
        self.scopes = scopes
    def run(self):
        try:
            flow = self.app.initiate_device_flow(scopes=self.scopes)
            if "user_code" not in flow:
                self.result.emit(None, Exception(flow.get("error_description") or "Falha ao iniciar Device Code Flow.")); return
            try:
                webbrowser.open(flow["verification_uri"])
            except Exception:
                pass
            token = self.app.acquire_token_by_device_flow(flow)
            if "access_token" in token:
                self.result.emit(token, None)
            else:
                self.result.emit(None, Exception(token.get("error_description") or str(token)))
        except Exception as e:
            self.result.emit(None, e)

def device_code_dialog(parent: QWidget, app: msal.PublicClientApplication) -> Optional[Dict]:
    dlg = QDialog(parent); dlg.setWindowTitle("Entrar no OneDrive"); dlg.resize(480, 220)
    lay = QVBoxLayout(dlg)
    lay.addWidget(QLabel("Abrindo a página da Microsoft para entrar.\nSe não abrir, acesse:"))
    url = QLabel("<a href='https://microsoft.com/devicelogin'>https://microsoft.com/devicelogin</a>")
    url.setOpenExternalLinks(True); lay.addWidget(url)
    lay.addWidget(QLabel("Conclua o login no navegador…"))
    bar = QProgressBar(); bar.setRange(0,0); lay.addWidget(bar)
    btns = QDialogButtonBox(QDialogButtonBox.Cancel); lay.addWidget(btns); btns.rejected.connect(dlg.reject)

    thread = MSALDeviceCodeThread(app, SCOPES)
    token_holder = {"tok": None, "err": None}
    def on_result(tok, err):
        token_holder["tok"] = tok; token_holder["err"] = err
        if err:
            QMessageBox.critical(dlg, "Erro", str(err)); dlg.reject()
        else:
            dlg.accept()
    thread.result.connect(on_result); thread.start()
    ok = dlg.exec_() == QDialog.Accepted
    thread.wait(50)
    return token_holder["tok"] if ok else None

def try_authorities(parent: QWidget, create_app_fn, state) -> Optional[Dict]:
    errors = []
    for auth in [state["onedrive"].get("authority")] + [a for a in AUTHORITIES if a != state["onedrive"].get("authority")]:
        if not auth:
            continue
        app = create_app_fn(auth)
        # tenta device code nessa autoridade
        tok = device_code_dialog(parent, app)
        if tok and "access_token" in tok:
            state["onedrive"]["authority"] = auth
            save_state(state)
            return tok
        else:
            errors.append(f"{auth}: falhou")
    if errors:
        QMessageBox.critical(parent, "OneDrive", "Falha ao iniciar Device Code Flow:\n\n" + "\n".join(errors))
    return None
