import json
from pathlib import Path
from typing import Any, Dict
from .config import APP_SUPPORT, DEFAULT_LIBRARY

STATE_FILE = APP_SUPPORT / "state.json"

def _default_onedrive_section():
    return {
        "folder_id": None,
        "folder_path": None,
        "include_subfolders": True,
        "account_label": None,
        "authority": None,
    }

def _default_gdrive_section():
    return {
        "folder_id": None,
        "folder_path": None,
        "include_subfolders": True,
        "account_label": None,
    }

def default_state() -> Dict[str, Any]:
    return {
        "library_dir": str(DEFAULT_LIBRARY),
        "last_page_by_file": {},
        "onedrive": _default_onedrive_section(),
        "gdrive": _default_gdrive_section(),
        "ui_view_mode": "list",
        "ui_thumb_size": 160,
    }

def load_state() -> Dict[str, Any]:
    base = default_state()
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            base.update(data)
        except Exception:
            pass
    # garante seções
    od = base.setdefault("onedrive", _default_onedrive_section())
    for k, v in _default_onedrive_section().items():
        od.setdefault(k, v)
    gd = base.setdefault("gdrive", _default_gdrive_section())
    for k, v in _default_gdrive_section().items():
        gd.setdefault(k, v)
    return base

def save_state(state: Dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, ensure_ascii=False)
