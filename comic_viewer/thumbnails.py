import hashlib
import json
import logging
import subprocess
from pathlib import Path
from typing import Optional, Tuple, List

from PyQt5.QtGui import QImage, QPixmap
from .config import APP_SUPPORT
from .utils import detect_unar, detect_lsar
import zipfile

log = logging.getLogger("thumbs")

THUMBS_DIR = APP_SUPPORT / "thumbnails"
THUMBS_DIR.mkdir(parents=True, exist_ok=True)

UNAR_PATH = detect_unar()
LSAR_PATH = detect_lsar()

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

def _archive_fingerprint(archive: Path) -> str:
    st = archive.stat()
    raw = f"{archive.resolve()}|{st.st_mtime_ns}|{st.st_size}".encode("utf-8")
    return hashlib.sha1(raw).hexdigest()

# ---------- CBZ ----------
def _cbz_first_image_bytes(archive: Path) -> Optional[bytes]:
    try:
        with zipfile.ZipFile(archive, "r") as zf:
            names: List[str] = [n for n in zf.namelist() if Path(n).suffix.lower() in IMAGE_EXTS]
            names.sort(key=lambda s: s.lower())
            if not names:
                log.debug(f"[CBZ] sem imagens: {archive.name}")
                return None
            first = names[0]
            log.debug(f"[CBZ] primeira imagem: {first}")
            with zf.open(first, "r") as f:
                return f.read()
    except Exception as e:
        log.exception(f"[CBZ] erro lendo {archive.name}: {e}")
        return None

# ---------- CBR ----------
def _cbr_first_image_name_with_lsar(archive: Path) -> Optional[str]:
    if not LSAR_PATH:
        log.warning("[CBR] lsar não disponível")
        return None
    try:
        proc = subprocess.run(
            [LSAR_PATH, "-json", str(archive)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
        )
        data = json.loads(proc.stdout.decode("utf-8", errors="ignore"))
        items = data.get("lsarContents") or data.get("files") or []
        candidates = []
        for it in items:
            name = it.get("XADFileName") or it.get("Name") or it.get("name")
            if name and Path(name).suffix.lower() in IMAGE_EXTS:
                candidates.append(name)
        candidates.sort(key=lambda s: s.lower())
        if not candidates:
            log.debug(f"[CBR] sem imagens listáveis em: {archive.name}")
            return None
        log.debug(f"[CBR] primeira imagem: {candidates[0]}")
        return candidates[0]
    except subprocess.CalledProcessError as e:
        log.error(f"[CBR] lsar falhou ({archive.name}): {e.stderr.decode('utf-8', 'ignore')}")
        return None
    except Exception as e:
        log.exception(f"[CBR] erro listando {archive.name}: {e}")
        return None

def _cbr_extract_single_file_bytes(archive: Path, inner_name: str) -> Optional[bytes]:
    """
    Extrai só um arquivo do CBR usando unar.
    - Usa '-no-directory' para evitar pasta com nome do .rar.
    - Se o 'leaf' não for encontrado (normalização/renomeações),
      faz fallback: pega a PRIMEIRA imagem encontrada no tmp, recursivamente.
    """
    if not UNAR_PATH:
        log.warning("[CBR] unar não disponível")
        return None

    tmpdir = THUMBS_DIR / "_tmp"
    tmpdir.mkdir(parents=True, exist_ok=True)
    # limpa sobras antigas
    for p in tmpdir.glob("*"):
        try:
            if p.is_file():
                p.unlink()
            elif p.is_dir():
                for f in p.glob("**/*"):
                    try: f.unlink()
                    except Exception: pass
                try: p.rmdir()
                except Exception: pass
        except Exception:
            pass

    try:
        cmd = [
            UNAR_PATH,
            "-quiet",
            "-force-overwrite",
            "-no-directory",
            "-output-directory", str(tmpdir),
            str(archive),
            inner_name,
        ]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            log.error(f"[CBR] unar falhou ({archive.name}) rc={proc.returncode}: {proc.stderr.decode('utf-8','ignore')}")
            return None

        # 1) Tenta pelo basename exato
        leaf = Path(inner_name).name
        direct = tmpdir / leaf
        if direct.exists() and direct.is_file():
            log.debug(f"[CBR] extraído (direto): {direct}")
            return direct.read_bytes()

        # 2) Procura recursivamente pelo basename
        matches = list(tmpdir.rglob(leaf))
        if matches:
            log.debug(f"[CBR] extraído (rglob): {matches[0]}")
            return matches[0].read_bytes()

        # 3) Fallback final: pegue QUALQUER imagem extraída e use a primeira (ordenada)
        images = [p for p in tmpdir.rglob("*") if p.is_file() and p.suffix.lower() in IMAGE_EXTS]
        images.sort(key=lambda p: p.as_posix().lower())
        if images:
            log.debug(f"[CBR] fallback: usando primeira imagem encontrada: {images[0]}")
            return images[0].read_bytes()

        log.error(f"[CBR] unar não produziu '{leaf}' nem qualquer imagem em {tmpdir}")
        return None

    except Exception as e:
        log.exception(f"[CBR] erro extrair {inner_name} de {archive.name}: {e}")
        return None

# ---------- imagem ----------
def _qimage_from_bytes(data: bytes, target_size: Tuple[int, int]) -> Optional[QImage]:
    img = QImage()
    ok = img.loadFromData(data)
    if not ok or img.isNull():
        log.debug("[IMG] falha ao carregar QImage a partir dos bytes")
        return None
    w, h = target_size
    return img.scaled(w, h, 1, 1)  # Qt.KeepAspectRatio=1, Qt.SmoothTransformation=1

def make_thumbnail(archive: Path, size: int = 256) -> Optional[QPixmap]:
    fid = _archive_fingerprint(archive)
    cache_file = THUMBS_DIR / f"{fid}.png"

    # Cache
    if cache_file.exists():
        pix = QPixmap(str(cache_file))
        if not pix.isNull():
            log.debug(f"[CACHE] hit para {archive.name}")
            return pix
        else:
            log.debug(f"[CACHE] corrompido (apagando): {cache_file}")
            try: cache_file.unlink()
            except Exception: pass

    ext = archive.suffix.lower()
    data: Optional[bytes] = None

    log.info(f"[THUMB] gerando para {archive.name} ({ext})")

    if ext == ".cbz":
        data = _cbz_first_image_bytes(archive)
    elif ext == ".cbr":
        inner = _cbr_first_image_name_with_lsar(archive)
        if inner:
            data = _cbr_extract_single_file_bytes(archive, inner)
    else:
        log.warning(f"[THUMB] extensão não suportada: {ext}")
        return None

    if not data:
        log.warning(f"[THUMB] não foi possível obter bytes de imagem para {archive.name}")
        return None

    qimg = _qimage_from_bytes(data, (size, size))
    if not qimg:
        log.warning(f"[THUMB] QImage inválida para {archive.name}")
        return None

    # salva e retorna
    ok = qimg.save(str(cache_file), "PNG")
    if not ok:
        log.warning(f"[THUMB] falhou ao salvar cache em {cache_file}")
    else:
        log.debug(f"[CACHE] salvo em {cache_file}")

    return QPixmap.fromImage(qimg)
