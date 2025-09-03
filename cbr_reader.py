import os
import sys
import json
import time
import webbrowser
import subprocess
from pathlib import Path
from typing import List, Optional, Dict

import requests
import msal
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QIcon
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFileDialog, QMessageBox,
    QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel,
    QPushButton, QSplitter, QLineEdit, QSlider, QAction, QToolBar,
    QDialog, QDialogButtonBox, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QProgressBar
)

# ================== CONFIG ==================
APP_NAME = "CBRReaderPy"
DEFAULT_LIBRARY = Path.home() / "CBRLibrary"
APP_SUPPORT = Path.home() / "Library" / "Application Support" / APP_NAME
APP_SUPPORT.mkdir(parents=True, exist_ok=True)
STATE_FILE = APP_SUPPORT / "state.json"

# OneDrive / MSAL
CLIENT_ID = "YOUR_CLIENT_ID_HERE"  # <<< COLOQUE SEU CLIENT_ID
AUTHORITY = "https://login.microsoftonline.com/common"
SCOPES = ["Files.Read", "offline_access"]
MSAL_CACHE_FILE = APP_SUPPORT / "msal_cache.bin"

# ================== ESTADO ==================
def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "library_dir": str(DEFAULT_LIBRARY),
        "last_page_by_file": {},
        "onedrive": {
            "folder_id": None,
            "folder_path": None,
            "include_subfolders": True,
            "account_label": None   # exibimos “Conectado como …”
        }
    }

def save_state(state: dict):
    try:
        STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print("Falha ao salvar estado:", e)

# ================== UNAR / EXTRAÇÃO ==================
def detect_unar() -> str:
    for c in ["/usr/local/bin/unar", "/opt/homebrew/bin/unar", "/usr/bin/unar"]:
        if Path(c).exists():
            return c
    return ""
UNAR_PATH = detect_unar()

class CBRExtractor:
    @staticmethod
    def extract(archive_path: Path) -> Path:
        if not UNAR_PATH:
            raise RuntimeError("Ferramenta 'unar' não encontrada. Instale com: brew install unar")
        tmp_root = APP_SUPPORT / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        out_dir = tmp_root / archive_path.stem
        if out_dir.exists():
            for p in out_dir.rglob("*"):
                try: p.unlink()
                except IsADirectoryError: pass
                except Exception: pass
            for p in sorted(out_dir.rglob("*"), reverse=True):
                if p.is_dir():
                    try: p.rmdir()
                    except Exception: pass
        out_dir.mkdir(parents=True, exist_ok=True)

        cmd = [UNAR_PATH, "-quiet", "-force-overwrite", "-output-directory", str(out_dir), str(archive_path)]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            raise RuntimeError(f"Falha ao extrair: {proc.stderr.decode('utf-8', errors='ignore')}")
        return out_dir

    @staticmethod
    def list_images(dir_path: Path) -> List[Path]:
        exts = {".jpg", ".jpeg", ".png", ".webp"}
        imgs = [p for p in dir_path.rglob("*") if p.suffix.lower() in exts]
        imgs.sort(key=lambda p: p.name.lower())
        return imgs

# ================== LEITOR ==================
class ReaderWindow(QMainWindow):
    def __init__(self, file_path: Path, state: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{APP_NAME} — {file_path.name}")
        self.setWindowIcon(QIcon.fromTheme("book"))
        self.file_path = file_path
        self.state = state
        self.images_paths: List[Path] = []
        self.current_index = 0
        self.zoom = 100

        central = QWidget(); self.setCentralWidget(central)
        v = QVBoxLayout(central)

        self.info_label = QLabel("Abrindo…"); self.info_label.setAlignment(Qt.AlignCenter)
        self.image_label = QLabel(); self.image_label.setAlignment(Qt.AlignCenter)

        controls = QHBoxLayout()
        self.prev_btn = QPushButton("◀︎"); self.next_btn = QPushButton("▶︎")
        self.page_slider = QSlider(Qt.Horizontal); self.page_slider.setMinimum(1); self.page_slider.setMaximum(1); self.page_slider.setValue(1)
        self.page_slider.setTickInterval(1); self.page_slider.setSingleStep(1)
        self.zoom_slider = QSlider(Qt.Horizontal); self.zoom_slider.setMinimum(25); self.zoom_slider.setMaximum(300); self.zoom_slider.setValue(self.zoom)
        self.page_label = QLabel("0/0"); self.zoom_label = QLabel(f"{self.zoom}%")

        controls.addWidget(self.prev_btn); controls.addWidget(self.next_btn)
        controls.addWidget(QLabel("Página:")); controls.addWidget(self.page_slider, 1); controls.addWidget(self.page_label)
        controls.addSpacing(12); controls.addWidget(QLabel("Zoom:")); controls.addWidget(self.zoom_slider); controls.addWidget(self.zoom_label)

        v.addWidget(self.info_label); v.addWidget(self.image_label, 1); v.addLayout(controls)

        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)
        self.page_slider.valueChanged.connect(self.goto_page)
        self.zoom_slider.valueChanged.connect(self.set_zoom)

        QTimer.singleShot(10, self._open_and_show)
        self.resize(1000, 800)

    def _open_and_show(self):
        try:
            out_dir = CBRExtractor.extract(self.file_path)
            self.images_paths = CBRExtractor.list_images(out_dir)
            if not self.images_paths:
                raise RuntimeError("Não encontrei imagens dentro do arquivo.")
            self.page_slider.setMaximum(len(self.images_paths))
            last = self.state.get("last_page_by_file", {}).get(str(self.file_path), 1)
            last = max(1, min(last, len(self.images_paths)))
            self.page_slider.setValue(last)
            self._render_page(last - 1)
            self.info_label.setText("")
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e)); self.close()

    def _render_page(self, index: int):
        self.current_index = index
        self.page_label.setText(f"{index+1}/{len(self.images_paths)}")
        img_path = self.images_paths[index]
        pix = QPixmap(str(img_path))
        if pix.isNull():
            self.image_label.setText("Falha ao carregar a imagem."); return
        if self.zoom != 100:
            w = int(pix.width() * (self.zoom/100.0)); h = int(pix.height() * (self.zoom/100.0))
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            avail_w = max(400, self.image_label.width()-20); avail_h = max(300, self.image_label.height()-20)
            pix = pix.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.image_label.setPixmap(pix)
        self.state.setdefault("last_page_by_file", {})[str(self.file_path)] = index + 1
        save_state(self.state)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.images_paths:
            self._render_page(self.current_index)

    def prev_page(self):
        if self.current_index > 0:
            self.page_slider.setValue(self.current_index)
            self._render_page(self.current_index - 1)

    def next_page(self):
        if self.current_index < len(self.images_paths) - 1:
            self.page_slider.setValue(self.current_index + 2)
            self._render_page(self.current_index + 1)

    def goto_page(self, val: int):
        if self.images_paths:
            idx = max(0, min(val - 1, len(self.images_paths)-1))
            self._render_page(idx)

    def set_zoom(self, val: int):
        self.zoom = val; self.zoom_label.setText(f"{val}%")
        if self.images_paths:
            self._render_page(self.current_index)

# ================== MSAL HELPERS ==================
class TokenCache:
    def __init__(self, path: Path):
        self.path = path
        self.cache = msal.SerializableTokenCache()
        self._load()
    def _load(self):
        if self.path.exists():
            try: self.cache.deserialize(self.path.read_text())
            except Exception: pass
    def persist(self):
        if self.cache.has_state_changed:
            self.path.write_text(self.cache.serialize())

class MSALDeviceCodeThread(QThread):
    result = pyqtSignal(object, object)
    def __init__(self, app: msal.PublicClientApplication, scopes: List[str]):
        super().__init__(); self.app = app; self.scopes = scopes
    def run(self):
        try:
            flow = self.app.initiate_device_flow(scopes=self.scopes)
            if "user_code" not in flow:
                self.result.emit(None, Exception("Falha ao iniciar Device Code Flow.")); return
            try: webbrowser.open(flow["verification_uri"])
            except Exception: pass
            token = self.app.acquire_token_by_device_flow(flow)
            if "access_token" in token:
                self.result.emit(token, None)
            else:
                self.result.emit(None, Exception(token.get("error_description") or str(token)))
        except Exception as e:
            self.result.emit(None, e)

# ================== ONEDRIVE CLIENT ==================
class OneDriveClient:
    def __init__(self, state: dict):
        self.state = state
        self.cache = TokenCache(MSAL_CACHE_FILE)
        self.app = msal.PublicClientApplication(client_id=CLIENT_ID, authority=AUTHORITY, token_cache=self.cache.cache)

    # ---------- Sessão ----------
    def _get_token_silent(self) -> Optional[Dict]:
        accounts = self.app.get_accounts()
        if accounts:
            tok = self.app.acquire_token_silent(SCOPES, account=accounts[0])
            if tok and "access_token" in tok:
                return tok
        return None

    def ensure_token(self, parent: QWidget) -> Optional[Dict]:
        # 1) tenta silencioso (como CDisplayEX)
        tok = self._get_token_silent()
        if tok:
            return tok
        # 2) inicia Device Code uma única vez
        dlg = QDialog(parent); dlg.setWindowTitle("Entrar no OneDrive"); dlg.resize(480, 220)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Abrindo a página da Microsoft para entrar.\nSe não abrir, acesse:"))
        url = QLabel("<a href='https://microsoft.com/devicelogin'>https://microsoft.com/devicelogin</a>")
        url.setOpenExternalLinks(True); lay.addWidget(url)
        hint = QLabel("Conclua o login no navegador…"); lay.addWidget(hint)
        bar = QProgressBar(); bar.setRange(0,0); lay.addWidget(bar)
        btns = QDialogButtonBox(QDialogButtonBox.Cancel); lay.addWidget(btns); btns.rejected.connect(dlg.reject)
        thread = MSALDeviceCodeThread(self.app, SCOPES)
        def on_result(token, err):
            if err:
                QMessageBox.critical(dlg, "Erro", str(err)); dlg.reject()
            else:
                self.cache.persist()
                dlg.accept()
        thread.result.connect(on_result); thread.start()
        ok = dlg.exec_() == QDialog.Accepted
        thread.wait(50)
        return self._get_token_silent() if ok else None

    def sign_out(self):
        # remove todas as contas do cache
        for acc in self.app.get_accounts():
            self.app.remove_account(acc)
        self.cache.persist()
        if MSAL_CACHE_FILE.exists():
            try: MSAL_CACHE_FILE.unlink()
            except Exception: pass

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

    # ---------- Pastas & arquivos ----------
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
            children = self.list_children(token, fid)
            for item in children:
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

# ================== DIALOG: SELETOR DE PASTAS ==================
class OneDriveFolderPicker(QDialog):
    def __init__(self, od: OneDriveClient, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escolher pasta do OneDrive"); self.resize(600, 420)
        self.od = od
        self.token = self.od.ensure_token(self)
        if not self.token:
            QTimer.singleShot(0, self.reject); return

        v = QVBoxLayout(self)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Nome", "ID"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        v.addWidget(self.tree)

        self.btn_recursive = QPushButton("Incluir subpastas: ON")
        self.btn_recursive.setCheckable(True); self.btn_recursive.setChecked(True)
        self.btn_recursive.clicked.connect(self._toggle_recursive)
        v.addWidget(self.btn_recursive, alignment=Qt.AlignLeft)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

        self._load_root()

    def _toggle_recursive(self):
        on = self.btn_recursive.isChecked()
        self.btn_recursive.setText(f"Incluir subpastas: {'ON' if on else 'OFF'}")

    def _load_root(self):
        self.tree.clear()
        try:
            children = self.od.list_children(self.token, None)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao listar OneDrive root:\n{e}")
            self.reject(); return
        for it in children:
            if it.get("folder"):
                node = QTreeWidgetItem([it["name"], it["id"]])
                node.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                self.tree.addTopLevelItem(node)
        self.tree.itemExpanded.connect(self._expand_item)

    def _expand_item(self, item: QTreeWidgetItem):
        folder_id = item.text(1)
        try:
            children = self.od.list_children(self.token, folder_id)
            item.takeChildren()
            for it in children:
                if it.get("folder"):
                    node = QTreeWidgetItem([it["name"], it["id"]])
                    node.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                    item.addChild(node)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao abrir pasta:\n{e}")

    def selected(self) -> Optional[Dict]:
        it = self.tree.currentItem()
        if not it: return None
        return {"id": it.text(1), "name": it.text(0), "recursive": self.btn_recursive.isChecked()}

# ================== THREAD: SYNC ==================
class OneDriveSyncThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, od: OneDriveClient, library_dir: Path, folder_id: str, recursive: bool):
        super().__init__()
        self.od = od; self.library_dir = library_dir; self.folder_id = folder_id; self.recursive = recursive

    def run(self):
        token = self.od.ensure_token(None)
        if not token:
            self.failed.emit("Não autenticado no OneDrive."); return
        try:
            items = list(self.od.iter_cbr_files(token, self.folder_id, self.recursive))
            total = len(items); done = 0; downloaded = 0
            existing = {p.name: p.stat().st_size for p in self.library_dir.glob("**/*") if p.suffix.lower() in (".cbr",".cbz")}
            for it in items:
                done += 1
                name = it["name"]; size = int(it.get("size", 0))
                dest = self.library_dir / name
                self.progress.emit(done, total, f"{done}/{total} verificando {name}")
                if dest.exists() and dest.stat().st_size == size and name in existing:
                    continue
                self.progress.emit(done, total, f"{done}/{total} baixando {name}")
                data = self.od.download_file(token, it["id"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f: f.write(data)
                downloaded += 1
                time.sleep(0.02)
            self.finished_ok.emit(downloaded)
        except Exception as e:
            self.failed.emit(str(e))

# ================== MAIN WINDOW ==================
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME); self.setWindowIcon(QIcon.fromTheme("folder-pictures"))
        self.state = load_state()
        self.library_dir = Path(self.state.get("library_dir", str(DEFAULT_LIBRARY))); self.library_dir.mkdir(parents=True, exist_ok=True)
        self.od = OneDriveClient(self.state)

        splitter = QSplitter(); left = QWidget(); right = QWidget()
        left_layout = QVBoxLayout(left); right_layout = QVBoxLayout(right)
        splitter.addWidget(left); splitter.addWidget(right); splitter.setStretchFactor(0,0); splitter.setStretchFactor(1,1)

        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Buscar por nome…")
        self.list_widget = QListWidget(); self.list_widget.itemDoubleClicked.connect(self.open_selected)
        left_layout.addWidget(self.search_edit); left_layout.addWidget(self.list_widget, 1)

        self.preview_label = QLabel(); self.preview_label.setAlignment(Qt.AlignCenter)
        right_layout.addWidget(self.preview_label, 1)

        self.setCentralWidget(splitter)

        tb = QToolBar("Ações"); self.addToolBar(tb)
        act_refresh = QAction("Atualizar", self); act_refresh.triggered.connect(self.refresh_list); tb.addAction(act_refresh)
        act_change_dir = QAction("Alterar pasta...", self); act_change_dir.triggered.connect(self.change_library_dir); tb.addAction(act_change_dir)
        act_open = QAction("Abrir selecionado", self); act_open.triggered.connect(self.open_selected); tb.addAction(act_open)
        tb.addSeparator()

        self.act_login = QAction("Conectar OneDrive", self); self.act_login.triggered.connect(self.connect_onedrive); tb.addAction(self.act_login)
        self.act_pick = QAction("Escolher pasta OneDrive…", self); self.act_pick.triggered.connect(self.pick_onedrive_folder); tb.addAction(self.act_pick)
        self.act_sync = QAction("Sincronizar OneDrive", self); self.act_sync.triggered.connect(self.sync_onedrive); tb.addAction(self.act_sync)
        tb.addSeparator()
        self.act_logout = QAction("Sair do OneDrive", self); self.act_logout.triggered.connect(self.logout_onedrive); tb.addAction(self.act_logout)

        self.search_edit.textChanged.connect(self.apply_filter)

        self.all_files: List[Path] = []
        self.refresh_list()
        self._update_right_panel()
        self.resize(1200, 720)

        # Tenta login silencioso ao abrir (para ficar “logado para sempre”).
        QTimer.singleShot(50, self._silent_signin_and_update)

    # ---------- UI helpers ----------
    def _update_right_panel(self):
        od_cfg = self.state.get("onedrive", {})
        folder = od_cfg.get("folder_path") or "(não selecionada)"
        acct = od_cfg.get("account_label") or "(desconectado)"
        self.preview_label.setText(
            "Selecione um arquivo .cbr/.cbz na lista à esquerda para abrir.\n"
            f"Pasta da biblioteca:\n{self.library_dir}\n\n"
            f"Pasta OneDrive: {folder}\n"
            f"Status OneDrive: {acct}"
        )

    def _set_account_label_from_token(self, token: Optional[Dict]):
        if token:
            label = self.od.get_profile_label(token)
            self.state["onedrive"]["account_label"] = label
            save_state(self.state)
        else:
            self.state["onedrive"]["account_label"] = None
            save_state(self.state)
        self._update_right_panel()

    def _silent_signin_and_update(self):
        tok = self.od._get_token_silent()
        self._set_account_label_from_token(tok)

    # ---------- Biblioteca ----------
    def refresh_list(self):
        self.all_files = self._find_archives(self.library_dir)
        self.apply_filter()

    def _find_archives(self, base_dir: Path) -> List[Path]:
        exts = {".cbr", ".cbz"}; files = []
        for root, _, names in os.walk(base_dir):
            for f in names:
                p = Path(root) / f
                if p.suffix.lower() in exts: files.append(p)
        files.sort(key=lambda p: p.name.lower()); return files

    def apply_filter(self):
        q = self.search_edit.text().strip().lower()
        self.list_widget.clear()
        for p in self.all_files:
            if not q or q in p.name.lower():
                it = QListWidgetItem(p.name); it.setToolTip(str(p)); it.setData(Qt.UserRole, str(p))
                it.setIcon(QIcon.fromTheme("image-x-generic")); self.list_widget.addItem(it)

    def change_library_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Escolher pasta da biblioteca", str(self.library_dir))
        if path:
            self.library_dir = Path(path)
            self.state["library_dir"] = str(self.library_dir); save_state(self.state)
            self._update_right_panel()
            self.refresh_list()

    def open_selected(self):
        it = self.list_widget.currentItem()
        if not it: return
        file_path = Path(it.data(Qt.UserRole))
        if not file_path.exists():
            QMessageBox.warning(self, "Aviso", "Arquivo não encontrado."); self.refresh_list(); return
        ReaderWindow(file_path, self.state, self).show()

    # ---------- OneDrive ----------
    def connect_onedrive(self):
        tok = self.od.ensure_token(self)
        if tok:
            self._set_account_label_from_token(tok)
            QMessageBox.information(self, "OneDrive", "Autenticado com sucesso.")
        else:
            QMessageBox.warning(self, "OneDrive", "Login cancelado.")

    def pick_onedrive_folder(self):
        picker = OneDriveFolderPicker(self.od, self)
        if picker.result() == QDialog.Accepted:
            sel = picker.selected()
            if not sel:
                QMessageBox.warning(self, "OneDrive", "Nenhuma pasta selecionada."); return
            self.state["onedrive"]["folder_id"] = sel["id"]
            self.state["onedrive"]["folder_path"] = sel["name"]
            self.state["onedrive"]["include_subfolders"] = bool(sel["recursive"])
            save_state(self.state)
            self._update_right_panel()
            QMessageBox.information(self, "OneDrive", f"Pasta selecionada: {sel['name']}")

    def sync_onedrive(self):
        cfg = self.state.get("onedrive", {})
        folder_id = cfg.get("folder_id")
        if not folder_id:
            QMessageBox.information(self, "OneDrive", "Escolha uma pasta do OneDrive primeiro.")
            return
        recursive = bool(cfg.get("include_subfolders", True))

        dlg = QDialog(self); dlg.setWindowTitle("Sincronizando OneDrive…"); dlg.resize(420,150)
        v = QVBoxLayout(dlg)
        lab = QLabel("Baixando arquivos .cbr/.cbz…"); v.addWidget(lab)
        bar = QProgressBar(); bar.setRange(0, 100); v.addWidget(bar)
        status = QLabel(); status.setWordWrap(True); v.addWidget(status)
        btns = QDialogButtonBox(QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.rejected.connect(dlg.reject)

        th = OneDriveSyncThread(self.od, self.library_dir, folder_id, recursive)
        def on_prog(done, total, msg):
            status.setText(msg)
            if total>0: bar.setValue(int(done*100/total))
        def on_ok(n):
            status.setText(f"Concluído. Novos arquivos: {n}")
            bar.setValue(100)
            self.refresh_list()
        def on_fail(err):
            status.setText(f"Erro: {err}")
        th.progress.connect(on_prog); th.finished_ok.connect(on_ok); th.failed.connect(on_fail)
        th.start()
        dlg.exec_()
        th.wait(50)
        self.refresh_list()

    def logout_onedrive(self):
        self.od.sign_out()
        self.state["onedrive"]["account_label"] = None
        save_state(self.state)
        self._update_right_panel()
        QMessageBox.information(self, "OneDrive", "Sessão encerrada.")

# ================== MAIN ==================
def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME); app.setOrganizationName(APP_NAME)
    DEFAULT_LIBRARY.mkdir(parents=True, exist_ok=True)
    win = MainWindow(); win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
