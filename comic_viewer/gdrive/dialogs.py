from __future__ import annotations
from typing import Optional, Dict
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QHeaderView,
    QDialogButtonBox, QPushButton, QMessageBox, QApplication, QLabel, QHBoxLayout
)
from PyQt5.QtCore import Qt, QTimer
from .client import GDriveClient

FOLDER_MIME = "application/vnd.google-apps.folder"

class GDriveFolderPicker(QDialog):
    def __init__(self, gd: GDriveClient, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escolher pasta do Google Drive")
        self.resize(640, 480)
        self.gd = gd
        if not self.gd.ensure_creds(self):
            self.reject(); return

        v = QVBoxLayout(self)

        # barra superior (status + recarregar)
        top = QHBoxLayout()
        self.status_lbl = QLabel("Carregando…")
        self.btn_reload = QPushButton("Recarregar")
        self.btn_reload.clicked.connect(self._load_my_drive)
        top.addWidget(self.status_lbl, 1)
        top.addWidget(self.btn_reload, 0, Qt.AlignRight)
        v.addLayout(top)

        self.tree = QTreeWidget()
        self.tree.setHeaderLabels(["Nome", "ID"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tree.setUniformRowHeights(True)
        v.addWidget(self.tree)

        self.btn_recursive = QPushButton("Incluir subpastas: ON")
        self.btn_recursive.setCheckable(True); self.btn_recursive.setChecked(True)
        self.btn_recursive.clicked.connect(self._toggle_recursive)
        v.addWidget(self.btn_recursive)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        v.addWidget(btns)
        btns.accepted.connect(self.accept)
        btns.rejected.connect(self.reject)

        self.tree.itemExpanded.connect(self._expand_item)

        QTimer.singleShot(0, self._load_my_drive)

    def _toggle_recursive(self):
        self.btn_recursive.setText(f"Incluir subpastas: {'ON' if self.btn_recursive.isChecked() else 'OFF'}")

    def _set_status(self, text: str):
        self.status_lbl.setText(text)

    def _load_my_drive(self):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._set_status("Carregando Meu Drive…")
        try:
            self.tree.clear()
            root = QTreeWidgetItem(["Meu Drive", "root"])
            root.setData(0, Qt.UserRole, {"loaded": False})
            root.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
            self.tree.addTopLevelItem(root)
            self._populate_children(root)   # carrega 1o nível
            root.setExpanded(True)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao listar raiz:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def _populate_children(self, item: QTreeWidgetItem):
        meta = item.data(0, Qt.UserRole) or {}
        if meta.get("loaded"):
            return
        fid = item.text(1)  # "root" ou id da pasta
        try:
            children = self.gd.list_children(fid)
            item.takeChildren()
            folders = [it for it in children if it["mimeType"] == FOLDER_MIME]
            for it in folders:
                node = QTreeWidgetItem([it["name"], it["id"]])
                node.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                node.setData(0, Qt.UserRole, {"loaded": False})
                item.addChild(node)
            meta["loaded"] = True
            item.setData(0, Qt.UserRole, meta)

            # feedback visual
            if item is self.tree.topLevelItem(0):  # se for o "Meu Drive"
                if len(folders) == 0:
                    self._set_status("Meu Drive: nenhuma pasta encontrada neste nível (apenas arquivos).")
                else:
                    self._set_status(f"Meu Drive: {len(folders)} pasta(s) encontradas.")
        except Exception as e:
            raise

    def _expand_item(self, item: QTreeWidgetItem):
        QApplication.setOverrideCursor(Qt.WaitCursor)
        self._set_status(f"Abrindo: {item.text(0)}…")
        try:
            self._populate_children(item)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao abrir pasta:\n{e}")
        finally:
            QApplication.restoreOverrideCursor()

    def selected(self) -> Optional[Dict]:
        it = self.tree.currentItem()
        if not it:
            return None
        return {
            "id": it.text(1),
            "name": it.text(0),
            "recursive": self.btn_recursive.isChecked()
        }
