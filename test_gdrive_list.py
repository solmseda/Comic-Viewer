from comic_viewer.gdrive.client import GDriveClient
from comic_viewer.state import load_state

gd = GDriveClient(load_state())
if gd.ensure_creds(None):
    print("Conta:", gd.account_label())
    items = gd.list_children("root")
    print(f"Total itens no nível do root: {len(items)}")
    folders = [it for it in items if it["mimeType"] == "application/vnd.google-apps.folder"]
    print(f"Pastas no root: {len(folders)}")
    for it in folders[:20]:
        print("📁", it["name"], it["id"])
else:
    print("Falhou autenticar")
