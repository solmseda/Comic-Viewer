from typing import Optional, Dict
from PyQt5.QtWidgets import QDialog, QVBoxLayout, QTreeWidget, QTreeWidgetItem, QHeaderView, QDialogButtonBox, QPushButton, QMessageBox
from ..onedrive.client import OneDriveClient

class OneDriveFolderPicker(QDialog):
    def __init__(self, od: OneDriveClient, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Escolher pasta do OneDrive")
        self.resize(600, 420)
        self.od = od
        self.token = self.od.ensure_token(self)
        if not self.token:
            self.reject(); return

        v = QVBoxLayout(self)
        self.tree = QTreeWidget(); self.tree.setHeaderLabels(["Nome", "ID"])
        self.tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        v.addWidget(self.tree)

        self.btn_recursive = QPushButton("Incluir subpastas: ON")
        self.btn_recursive.setCheckable(True); self.btn_recursive.setChecked(True)
        self.btn_recursive.clicked.connect(self._toggle_recursive)
        v.addWidget(self.btn_recursive)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel); v.addWidget(btns)
        btns.accepted.connect(self.accept); btns.rejected.connect(self.reject)

        self._load_root()

    def _toggle_recursive(self):
        self.btn_recursive.setText(f"Incluir subpastas: {'ON' if self.btn_recursive.isChecked() else 'OFF'}")

    def _load_root(self):
        self.tree.clear()
        try:
            for it in self.od.list_children(self.token, None):
                if it.get("folder"):
                    node = QTreeWidgetItem([it["name"], it["id"]])
                    node.setChildIndicatorPolicy(QTreeWidgetItem.ShowIndicator)
                    self.tree.addTopLevelItem(node)
        except Exception as e:
            QMessageBox.critical(self, "Erro", f"Falha ao listar root:\n{e}")
            self.reject(); return
        self.tree.itemExpanded.connect(self._expand_item)

    def _expand_item(self, item: QTreeWidgetItem):
        fid = item.text(1)
        try:
            item.takeChildren()
            for it in self.od.list_children(self.token, fid):
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
