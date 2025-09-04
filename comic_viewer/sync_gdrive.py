from pathlib import Path
from typing import Optional
from PyQt5.QtCore import QThread, pyqtSignal
from .gdrive.client import GDriveClient

class GDriveSyncThread(QThread):
    progress = pyqtSignal(int, int, str)
    finished_ok = pyqtSignal(int)
    failed = pyqtSignal(str)

    def __init__(self, gd: GDriveClient, library_dir: Path, folder_id: str, recursive: bool):
        super().__init__()
        self.gd = gd
        self.library_dir = library_dir
        self.folder_id = folder_id
        self.recursive = recursive

    def run(self):
        if not self.gd.ensure_creds(None):
            self.failed.emit("Não autenticado no Google Drive."); return
        try:
            items = list(self.gd.iter_cbr_files(self.folder_id or "root", self.recursive))
            total = len(items); done = 0; downloaded = 0
            existing = {p.name: p.stat().st_size for p in self.library_dir.glob("**/*") if p.suffix.lower() in (".cbr", ".cbz")}
            for it in items:
                done += 1
                name = it["name"]; size = int(it.get("size") or 0)
                dest = self.library_dir / name
                self.progress.emit(done, total, f"{done}/{total} verificando {name}")
                if dest.exists() and (size == 0 or dest.stat().st_size == size):
                    continue
                self.progress.emit(done, total, f"{done}/{total} baixando {name}")
                data = self.gd.download_file(it["id"])
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(dest, "wb") as f: f.write(data)
                downloaded += 1
            self.finished_ok.emit(downloaded)
        except Exception as e:
            self.failed.emit(str(e))
