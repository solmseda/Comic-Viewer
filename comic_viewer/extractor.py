import subprocess
from pathlib import Path
from typing import List
from .config import APP_SUPPORT
from .utils import detect_unar

UNAR_PATH = detect_unar()

class CBRExtractor:
    @staticmethod
    def extract(archive_path: Path) -> Path:
        if not UNAR_PATH:
            raise RuntimeError("Ferramenta 'unar' não encontrada. Instale com: brew install unar")

        tmp_root = APP_SUPPORT / "tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)
        out_dir = tmp_root / archive_path.stem

        # limpar pasta anterior
        if out_dir.exists():
            for p in out_dir.rglob("*"):
                try:
                    p.unlink()
                except IsADirectoryError:
                    pass
                except Exception:
                    pass
            for p in sorted(out_dir.rglob("*"), reverse=True):
                if p.is_dir():
                    try:
                        p.rmdir()
                    except Exception:
                        pass
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
