import logging
from pathlib import Path

log = logging.getLogger("utils")

def detect_unar() -> str:
    for c in ["/usr/local/bin/unar", "/opt/homebrew/bin/unar", "/usr/bin/unar"]:
        if Path(c).exists():
            log.debug(f"unar encontrado em: {c}")
            return c
    log.warning("unar NÃO encontrado")
    return ""

def detect_lsar() -> str:
    for c in ["/usr/local/bin/lsar", "/opt/homebrew/bin/lsar", "/usr/bin/lsar"]:
        if Path(c).exists():
            log.debug(f"lsar encontrado em: {c}")
            return c
    log.warning("lsar NÃO encontrado")
    return ""
