from PyQt5.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QLabel, QHBoxLayout,
    QPushButton, QSlider, QMessageBox, QToolBar, QAction,
    QLineEdit, QInputDialog
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap, QIcon, QIntValidator, QKeySequence
from pathlib import Path
from typing import List
from ..extractor import CBRExtractor
from ..state import save_state


class ReaderWindow(QMainWindow):
    def __init__(self, file_path: Path, state: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"CBRReaderPy — {file_path.name}")
        self.setWindowIcon(QIcon.fromTheme("book"))

        self.file_path = file_path
        self.state = state
        self.images_paths: List[Path] = []
        self.current_index = 0  # 0-based
        self.zoom = 100
        self._is_fullscreen = False

        self.setFocusPolicy(Qt.StrongFocus)

        # --- UI ---
        central = QWidget(); self.setCentralWidget(central)
        v = QVBoxLayout(central)

        tb = QToolBar("Leitor")
        self.addToolBar(tb)

        # Botões (setas tratadas somente em keyPressEvent)
        self.act_prev = QAction("◀︎ Anterior", self)
        self.act_prev.triggered.connect(self.prev_page)
        tb.addAction(self.act_prev)

        self.act_next = QAction("Próxima ▶︎", self)
        self.act_next.triggered.connect(self.next_page)
        tb.addAction(self.act_next)

        tb.addSeparator()

        # Ir para página… (atalhos: Cmd+G no mac, Ctrl+G no restante)
        self.act_goto = QAction("Ir para página…", self)
        self.act_goto.setShortcuts([QKeySequence("Meta+G"), QKeySequence("Ctrl+G")])
        self.act_goto.triggered.connect(self._prompt_goto)
        tb.addAction(self.act_goto)

        tb.addSeparator()

        self.act_full = QAction("Tela cheia", self)
        self.act_full.setShortcuts([Qt.Key_F11, Qt.Key_F])
        self.act_full.triggered.connect(self.toggle_fullscreen)
        tb.addAction(self.act_full)

        self.info_label = QLabel("Abrindo…")
        self.info_label.setAlignment(Qt.AlignCenter)

        self.image_label = QLabel()
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.setStyleSheet("background-color: #111;")

        ctr = QHBoxLayout()
        self.prev_btn = QPushButton("◀︎"); self.next_btn = QPushButton("▶︎")
        self.prev_btn.clicked.connect(self.prev_page)
        self.next_btn.clicked.connect(self.next_page)

        self.page_slider = QSlider(Qt.Horizontal)
        self.page_slider.setMinimum(1); self.page_slider.setMaximum(1); self.page_slider.setValue(1)
        self.page_slider.valueChanged.connect(self.goto_page)  # slider é 1-based

        self.page_label = QLabel("0/0")

        # Campo "Ir" (numérico) ao lado do slider
        self.page_input = QLineEdit()
        self.page_input.setFixedWidth(64)
        self.page_input.setAlignment(Qt.AlignCenter)
        self.page_input.setPlaceholderText("Ir…")
        self.page_input.setValidator(QIntValidator(1, 999999, self))  # max ajustado após abrir
        self.page_input.returnPressed.connect(self._jump_to_input)

        self.zoom_slider = QSlider(Qt.Horizontal)
        self.zoom_slider.setMinimum(25); self.zoom_slider.setMaximum(300); self.zoom_slider.setValue(self.zoom)
        self.zoom_slider.valueChanged.connect(self.set_zoom)
        self.zoom_label = QLabel(f"{self.zoom}%")

        ctr.addWidget(self.prev_btn)
        ctr.addWidget(self.next_btn)
        ctr.addWidget(QLabel("Página:"))
        ctr.addWidget(self.page_slider, 1)
        ctr.addWidget(self.page_label)
        ctr.addSpacing(8)
        ctr.addWidget(self.page_input)
        ctr.addSpacing(12)
        ctr.addWidget(QLabel("Zoom:"))
        ctr.addWidget(self.zoom_slider)
        ctr.addWidget(self.zoom_label)

        v.addWidget(self.info_label)
        v.addWidget(self.image_label, 1)
        v.addLayout(ctr)

        QTimer.singleShot(10, self._open_and_show)
        self.resize(1000, 800)

    # ---------- abertura e render ----------
    def _open_and_show(self):
        try:
            out_dir = CBRExtractor.extract(self.file_path)
            self.images_paths = CBRExtractor.list_images(out_dir)
            if not self.images_paths:
                raise RuntimeError("Não encontrei imagens dentro do arquivo.")
            total = len(self.images_paths)

            # configura limites dos controles
            self.page_slider.blockSignals(True)
            self.page_slider.setMaximum(total)
            self.page_slider.blockSignals(False)
            # atualiza range do input numérico
            self.page_input.setValidator(QIntValidator(1, total, self))
            self.page_input.setPlaceholderText(f"Ir… (1–{total})")

            # recupera última página (estado guarda 1-based)
            last = int(self.state.get("last_page_by_file", {}).get(str(self.file_path), 1))
            idx = max(0, min(last - 1, total - 1))

            self._go_to_index(idx)
            self.info_label.setText("")
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e)); self.close()

    def _render_page(self, index: int):
        """Renderiza a imagem do índice (0-based) e atualiza label + estado."""
        self.current_index = index
        total = len(self.images_paths)
        self.page_label.setText(f"{index+1}/{total}")
        # sincroniza o campo de entrada sem disparar retorno
        self.page_input.blockSignals(True)
        self.page_input.setText(str(index + 1))
        self.page_input.blockSignals(False)

        img_path = self.images_paths[index]
        pix = QPixmap(str(img_path))
        if pix.isNull():
            self.image_label.setText("Falha ao carregar a imagem.")
            return

        if self.zoom != 100:
            w = int(pix.width() * (self.zoom/100.0))
            h = int(pix.height() * (self.zoom/100.0))
            pix = pix.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        else:
            avail_w = max(400, self.image_label.width()-20)
            avail_h = max(300, self.image_label.height()-20)
            pix = pix.scaled(avail_w, avail_h, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        self.image_label.setPixmap(pix)

        # persiste última página (estado guarda 1-based)
        self.state.setdefault("last_page_by_file", {})[str(self.file_path)] = index + 1
        save_state(self.state)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.images_paths:
            self._render_page(self.current_index)

    # ---------- navegação centralizada ----------
    def _go_to_index(self, index: int):
        """Move para o índice desejado (0-based), sincronizando slider (1-based) sem efeitos colaterais."""
        if not self.images_paths:
            return
        index = max(0, min(index, len(self.images_paths) - 1))
        # sincroniza slider sem disparar goto_page
        self.page_slider.blockSignals(True)
        self.page_slider.setValue(index + 1)  # slider é 1-based
        self.page_slider.blockSignals(False)
        # renderiza uma única vez
        self._render_page(index)

    # slider -> vai para página (1-based -> 0-based)
    def goto_page(self, val: int):
        if not self.images_paths:
            return
        idx = max(0, min(val - 1, len(self.images_paths) - 1))
        self._render_page(idx)

    def prev_page(self):
        if self.images_paths and self.current_index > 0:
            self._go_to_index(self.current_index - 1)

    def next_page(self):
        if self.images_paths and self.current_index < len(self.images_paths) - 1:
            self._go_to_index(self.current_index + 1)

    def set_zoom(self, val: int):
        self.zoom = val
        self.zoom_label.setText(f"{val}%")
        if self.images_paths:
            self._render_page(self.current_index)

    # ---------- “Ir para página” ----------
    def _jump_to_input(self):
        """Enter no campo 'Ir…'."""
        if not self.images_paths:
            return
        txt = self.page_input.text().strip()
        if not txt:
            return
        try:
            page = int(txt)
        except ValueError:
            return
        total = len(self.images_paths)
        page = max(1, min(page, total))
        self._go_to_index(page - 1)

    def _prompt_goto(self):
        """Diálogo rápido via atalho (Cmd+G / Ctrl+G)."""
        if not self.images_paths:
            return
        total = len(self.images_paths)
        cur = self.current_index + 1
        page, ok = QInputDialog.getInt(self, "Ir para página", f"Digite um número de 1 a {total}:", cur, 1, total, 1)
        if ok:
            self._go_to_index(page - 1)

    # ---------- atalhos de teclado ----------
    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key_Right, Qt.Key_Down, Qt.Key_PageDown, Qt.Key_Space):
            self.next_page(); return
        if key in (Qt.Key_Left, Qt.Key_Up, Qt.Key_PageUp, Qt.Key_Backspace):
            self.prev_page(); return
        if key == Qt.Key_Home:
            self._go_to_index(0); return
        if key == Qt.Key_End:
            self._go_to_index(len(self.images_paths) - 1); return
        if key in (Qt.Key_F11, Qt.Key_F):
            self.toggle_fullscreen(); return
        if key == Qt.Key_Escape and self._is_fullscreen:
            self.toggle_fullscreen(); return
        super().keyPressEvent(event)

    # ---------- fullscreen ----------
    def toggle_fullscreen(self):
        if not self._is_fullscreen:
            self._is_fullscreen = True
            self.showFullScreen()
            self.act_full.setText("Sair da tela cheia")
        else:
            self._is_fullscreen = False
            self.showNormal()
            self.act_full.setText("Tela cheia")
