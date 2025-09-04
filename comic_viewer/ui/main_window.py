import os
import logging
from pathlib import Path
from typing import List

from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize
from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QSplitter, QLineEdit, QListWidget,
    QListWidgetItem, QAction, QToolBar, QFileDialog, QMessageBox, QDialog,
    QDialogButtonBox, QProgressBar, QFrame, QHBoxLayout, QToolButton, QMenu
)

from ..config import APP_NAME, DEFAULT_LIBRARY
from ..state import load_state, save_state
from ..onedrive.client import OneDriveClient
from ..onedrive.dialogs import OneDriveFolderPicker
from ..ui.reader_window import ReaderWindow
from ..sync import OneDriveSyncThread
from ..thumbnails import make_thumbnail

from ..gdrive.client import GDriveClient
from ..gdrive.dialogs import GDriveFolderPicker
from ..sync_gdrive import GDriveSyncThread

log = logging.getLogger("main")


# -------------------- Worker de thumbnails --------------------

class ThumbnailWorker(QThread):
    produced = pyqtSignal(str, QIcon)  # (filepath, icon)
    progress = pyqtSignal(int, int)    # done, total

    def __init__(self, files: List[Path], size: int):
        super().__init__()
        self.files = files
        self.size = size

    def run(self):
        total = len(self.files)
        log.info(f"[Worker] iniciando geração de thumbnails: {total} itens, size={self.size}")
        done = 0
        for p in self.files:
            try:
                pix = make_thumbnail(p, size=self.size)
                if pix and not pix.isNull():
                    icon = QIcon(pix)
                    self.produced.emit(str(p), icon)
                else:
                    log.warning(f"[Worker] thumbnail vazia para {p.name}")
            except Exception:
                log.exception(f"[Worker] erro gerando thumbnail para {p}")
            done += 1
            self.progress.emit(done, total)
        log.info("[Worker] finalizado")


# -------------------- Janela Principal --------------------

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.setWindowIcon(QIcon.fromTheme("folder-pictures"))

        # Estado
        self.state = load_state()
        self.library_dir = Path(self.state.get("library_dir", str(DEFAULT_LIBRARY)))
        self.library_dir.mkdir(parents=True, exist_ok=True)
        self.od = OneDriveClient(self.state)
        self.gd = GDriveClient(self.state)

        # Preferências de UI
        self.view_mode = self.state.get("ui_view_mode", "list")
        self.thumb_size = int(self.state.get("ui_thumb_size", 160))

        # Layout base
        splitter = QSplitter()
        left = QWidget(); right = QWidget()
        left_layout = QVBoxLayout(left)
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(8, 8, 8, 8)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 0)

        # ---- Esquerda (busca + lista)
        self.search_edit = QLineEdit(); self.search_edit.setPlaceholderText("Buscar por nome…")
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self.open_selected)
        left_layout.addWidget(self.search_edit)
        left_layout.addWidget(self.list_widget, 1)

        # ---- Direita (cartão pequeno)
        card_wrap = QHBoxLayout()
        card_wrap.addStretch(1)
        self.info_card = QFrame()
        self.info_card.setObjectName("infoCard")
        self.info_card.setFrameShape(QFrame.StyledPanel)
        self.info_card.setMaximumWidth(320)
        self.info_card.setStyleSheet("""
            QFrame#infoCard {
                border: 1px solid rgba(255,255,255,0.15);
                border-radius: 10px;
                padding: 12px;
                background: rgba(255,255,255,0.04);
            }
            QFrame#infoCard QLabel {
                font-size: 12px;
                line-height: 1.3em;
            }
        """)
        card_v = QVBoxLayout(self.info_card)
        self.info_label = QLabel(); self.info_label.setWordWrap(True)
        self.info_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        card_v.addWidget(self.info_label)
        card_wrap.addWidget(self.info_card, 0, Qt.AlignTop | Qt.AlignRight)
        right_layout.addLayout(card_wrap)
        right_layout.addStretch(1)

        self.setCentralWidget(splitter)

        # Toolbar
        tb = QToolBar("Ações")
        tb.setMovable(False)
        self.addToolBar(tb)

        # Ações básicas
        act_refresh = QAction("Atualizar", self);
        act_refresh.triggered.connect(self.refresh_list)
        act_change_dir = QAction("Alterar pasta...", self);
        act_change_dir.triggered.connect(self.change_library_dir)
        act_open = QAction("Abrir selecionado", self);
        act_open.triggered.connect(self.open_selected)

        tb.addAction(act_refresh)
        tb.addAction(act_change_dir)
        tb.addAction(act_open)
        tb.addSeparator()

        # Toggle Lista/Grade
        self.act_list = QAction("Lista", self);
        self.act_list.setCheckable(True)
        self.act_grid = QAction("Grade", self);
        self.act_grid.setCheckable(True)
        self.act_list.triggered.connect(lambda: self.set_view_mode("list"))
        self.act_grid.triggered.connect(lambda: self.set_view_mode("grid"))
        tb.addAction(self.act_list)
        tb.addAction(self.act_grid)
        tb.addSeparator()

        # --- Menu sanduíche OneDrive ---
        self.act_login = QAction("Conectar OneDrive", self);
        self.act_login.triggered.connect(self.connect_onedrive)
        self.act_pick = QAction("Escolher pasta OneDrive…", self);
        self.act_pick.triggered.connect(self.pick_onedrive_folder)
        self.act_sync = QAction("Sincronizar OneDrive", self);
        self.act_sync.triggered.connect(self.sync_onedrive)
        self.act_logout = QAction("Sair do OneDrive", self);
        self.act_logout.triggered.connect(self.logout_onedrive)

        od_menu = QMenu(self)
        od_menu.addAction(self.act_login)
        od_menu.addSeparator()
        od_menu.addAction(self.act_pick)
        od_menu.addAction(self.act_sync)
        od_menu.addSeparator()
        od_menu.addAction(self.act_logout)

        od_btn = QToolButton(self)
        od_btn.setText("OneDrive")
        od_btn.setIcon(QIcon.fromTheme("onedrive", QIcon()))  # se não houver ícone no tema, fica sem
        od_btn.setPopupMode(QToolButton.InstantPopup)
        od_btn.setMenu(od_menu)
        tb.addWidget(od_btn)

        # --- Menu sanduíche Google Drive ---
        self.act_gd_login = QAction("Conectar GDrive", self);
        self.act_gd_login.triggered.connect(self.connect_gdrive)
        self.act_gd_pick = QAction("Escolher pasta GDrive…", self);
        self.act_gd_pick.triggered.connect(self.pick_gdrive_folder)
        self.act_gd_sync = QAction("Sincronizar GDrive", self);
        self.act_gd_sync.triggered.connect(self.sync_gdrive)

        gd_menu = QMenu(self)
        gd_menu.addAction(self.act_gd_login)
        gd_menu.addSeparator()
        gd_menu.addAction(self.act_gd_pick)
        gd_menu.addAction(self.act_gd_sync)

        gd_btn = QToolButton(self)
        gd_btn.setText("Google Drive")
        gd_btn.setIcon(QIcon.fromTheme("google-drive", QIcon()))
        gd_btn.setPopupMode(QToolButton.InstantPopup)
        gd_btn.setMenu(gd_menu)
        tb.addWidget(gd_btn)

        self.search_edit.textChanged.connect(self.apply_filter)

        # Dados
        self.all_files: List[Path] = []
        self.thumb_worker: ThumbnailWorker = None  # type: ignore

        self.refresh_list()
        self._update_right_panel()
        self.resize(1200, 720)

        QTimer.singleShot(50, self._silent_signin_and_update)

    # -------- Painel direito --------
    def _update_right_panel(self):
        od_cfg = self.state.get("onedrive", {})
        folder = od_cfg.get("folder_path") or "(não selecionada)"
        acct = od_cfg.get("account_label") or "(desconectado)"
        gd_cfg = self.state.get("gdrive", {})
        gdfolder = gd_cfg.get("folder_path") or "(não selecionada)"
        gdacct = gd_cfg.get("account_label") or "(desconectado)"
        self.info_label.setText(
            "<b>Como usar</b><br>"
            "Selecione um arquivo <code>.cbr</code>/<code>.cbz</code> na lista para abrir.<br><br>"
            f"<b>Pasta da biblioteca</b><br>{self.library_dir}<br><br>"
            f"<b>Pasta OneDrive</b><br>{folder}<br>"
            f"<b>Status OneDrive</b><br>{acct}<br><br>"
            f"<b>Pasta Google Drive</b><br>{gdfolder}<br>"
            f"<b>Status Google Drive</b><br>{gdacct}"
        )

    def _set_account_label_from_token(self, token):
        if token:
            self.state["onedrive"]["account_label"] = self.od.get_profile_label(token)
        else:
            self.state["onedrive"]["account_label"] = None
        save_state(self.state)
        self._update_right_panel()

    def _silent_signin_and_update(self):
        tok = self.od._get_token_silent()
        self._set_account_label_from_token(tok)
        if self.gd.creds and self.gd.creds.valid:
            try:
                self.state["gdrive"]["account_label"] = self.gd.account_label()
                save_state(self.state)
                self._update_right_panel()
            except Exception:
                pass

    # -------- View mode --------
    def set_view_mode(self, mode: str):
        self.view_mode = mode
        self.state["ui_view_mode"] = mode
        save_state(self.state)

        if mode == "grid":
            self.list_widget.setViewMode(QListWidget.IconMode)
            self.list_widget.setIconSize(QSize(self.thumb_size, self.thumb_size))
            self.list_widget.setResizeMode(QListWidget.Adjust)
            self.list_widget.setGridSize(QSize(self.thumb_size + 32, self.thumb_size + 48))
            self.list_widget.setSpacing(10)
            self.list_widget.setAlternatingRowColors(False)
            self.list_widget.setUniformItemSizes(False)
            self.list_widget.setStyleSheet("")
        else:
            self.list_widget.setViewMode(QListWidget.ListMode)
            self.list_widget.setIconSize(QSize(28, 28))
            self.list_widget.setSpacing(1)
            self.list_widget.setAlternatingRowColors(True)
            self.list_widget.setUniformItemSizes(True)
            self.list_widget.setStyleSheet("""
                QListWidget::item { padding: 4px 6px; }
                QListWidget::item:selected { background: rgba(100,150,255,0.25); }
            """)

        self.act_list.setChecked(mode == "list")
        self.act_grid.setChecked(mode == "grid")
        self.apply_filter()

    # -------- Biblioteca --------
    def refresh_list(self):
        self.all_files = self._find_archives(self.library_dir)
        log.info(f"[UI] total de arquivos encontrados: {len(self.all_files)}")
        self.set_view_mode(self.view_mode)

    def _find_archives(self, base_dir: Path) -> List[Path]:
        exts = {".cbr", ".cbz"}
        files: List[Path] = []
        for root, _, names in os.walk(base_dir):
            for f in names:
                p = Path(root) / f
                if p.suffix.lower() in exts:
                    files.append(p)
        files.sort(key=lambda p: p.name.lower())
        return files

    def apply_filter(self):
        q = self.search_edit.text().strip().lower()
        self.list_widget.clear()
        visible_files: List[Path] = []
        for p in self.all_files:
            if not q or q in p.name.lower():
                it = QListWidgetItem(p.name)
                it.setToolTip(str(p))
                it.setData(Qt.UserRole, str(p))
                if self.view_mode == "grid":
                    it.setIcon(QIcon.fromTheme("image-x-generic"))
                else:
                    it.setIcon(QIcon.fromTheme("text-x-generic"))
                self.list_widget.addItem(it)
                visible_files.append(p)
        log.info(f"[UI] itens visíveis: {len(visible_files)} (modo={self.view_mode})")
        if self.view_mode == "grid" and visible_files:
            if getattr(self, "thumb_worker", None) and self.thumb_worker.isRunning():
                log.info("[UI] cancelando worker anterior")
                self.thumb_worker.terminate()
            self.thumb_worker = ThumbnailWorker(visible_files, size=self.thumb_size)
            self.thumb_worker.produced.connect(self._apply_thumbnail)
            self.thumb_worker.progress.connect(lambda d, t: log.debug(f"[UI] progresso thumbs: {d}/{t}"))
            self.thumb_worker.start()

    def _apply_thumbnail(self, filepath: str, icon: QIcon):
        for i in range(self.list_widget.count()):
            it = self.list_widget.item(i)
            if it.data(Qt.UserRole) == filepath:
                it.setIcon(icon)
                log.debug(f"[UI] thumbnail aplicada: {Path(filepath).name}")
                break

    def change_library_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Escolher pasta da biblioteca", str(self.library_dir))
        if path:
            self.library_dir = Path(path)
            self.state["library_dir"] = str(self.library_dir)
            save_state(self.state)
            self._update_right_panel()
            self.refresh_list()

    def open_selected(self):
        it = self.list_widget.currentItem()
        if not it: return
        file_path = Path(it.data(Qt.UserRole))
        if not file_path.exists():
            QMessageBox.warning(self, "Aviso", "Arquivo não encontrado.")
            self.refresh_list(); return
        ReaderWindow(file_path, self.state, self).show()

    # -------- OneDrive --------
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
            if not sel: return
            self.state["onedrive"]["folder_id"] = sel["id"]
            self.state["onedrive"]["folder_path"] = sel["name"]
            self.state["onedrive"]["include_subfolders"] = bool(sel["recursive"])
            save_state(self.state); self._update_right_panel()

    def sync_onedrive(self):
        od = self.state["onedrive"]
        folder_id = od.get("folder_id")
        if not folder_id:
            QMessageBox.information(self, "OneDrive", "Escolha uma pasta primeiro."); return
        recursive = bool(od.get("include_subfolders", True))
        dlg = QDialog(self); dlg.setWindowTitle("Sincronizando OneDrive…"); dlg.resize(420,150)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Baixando arquivos .cbr/.cbz…"))
        bar = QProgressBar(); bar.setRange(0,100); v.addWidget(bar)
        status = QLabel(); status.setWordWrap(True); v.addWidget(status)
        btns = QDialogButtonBox(QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.rejected.connect(dlg.reject)
        th = OneDriveSyncThread(self.od, self.library_dir, folder_id, recursive)
        th.progress.connect(lambda d,t,msg: (status.setText(msg), bar.setValue(int(d*100/t)) if t else None))
        th.finished_ok.connect(lambda n: (status.setText(f"Concluído. Novos: {n}"), bar.setValue(100), self.refresh_list()))
        th.failed.connect(lambda e: status.setText(f"Erro: {e}"))
        th.start(); dlg.exec_(); th.wait(50); self.refresh_list()

    def logout_onedrive(self):
        self.od.sign_out()
        self.state["onedrive"]["account_label"] = None
        save_state(self.state); self._update_right_panel()

    # -------- Google Drive --------
    def connect_gdrive(self):
        if self.gd.ensure_creds(self):
            self.state["gdrive"]["account_label"] = self.gd.account_label()
            save_state(self.state); self._update_right_panel()
            QMessageBox.information(self, "Google Drive", "Autenticado com sucesso.")
        else:
            QMessageBox.warning(self, "Google Drive", "Login cancelado.")

    def pick_gdrive_folder(self):
        picker = GDriveFolderPicker(self.gd, self)
        res = picker.exec_()  # <<< MOSTRA o diálogo
        if res == QDialog.Accepted:
            sel = picker.selected()
            if not sel:
                QMessageBox.warning(self, "Google Drive", "Nenhuma pasta selecionada.")
                return
            self.state["gdrive"]["folder_id"] = sel["id"]
            self.state["gdrive"]["folder_path"] = sel["name"]
            self.state["gdrive"]["include_subfolders"] = bool(sel["recursive"])
            save_state(self.state)
            self._update_right_panel()
            QMessageBox.information(self, "Google Drive", f"Pasta selecionada: {sel['name']}")

    def sync_gdrive(self):
        gd = self.state["gdrive"]
        folder_id = gd.get("folder_id") or "root"
        recursive = bool(gd.get("include_subfolders", True))
        if not self.gd.ensure_creds(self):
            QMessageBox.information(self, "Google Drive", "Conecte sua conta primeiro."); return

        dlg = QDialog(self); dlg.setWindowTitle("Sincronizando Google Drive…"); dlg.resize(420,150)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel("Baixando arquivos .cbr/.cbz…"))
        bar = QProgressBar(); bar.setRange(0, 100); v.addWidget(bar)
        status = QLabel(); status.setWordWrap(True); v.addWidget(status)
        btns = QDialogButtonBox(QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.rejected.connect(dlg.reject)

        th = GDriveSyncThread(self.gd, self.library_dir, folder_id, recursive)
        th.progress.connect(lambda d,t,msg: (status.setText(msg), bar.setValue(int(d*100/t)) if t else None))
        th.finished_ok.connect(lambda n: (status.setText(f"Concluído. Novos: {n}"), bar.setValue(100), self.refresh_list()))
        th.failed.connect(lambda e: status.setText(f"Erro: {e}"))

        th.start()
        dlg.exec_()
        th.wait(50)
        self.refresh_list()
