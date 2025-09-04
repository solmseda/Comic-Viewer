from PyQt5.QtWidgets import QApplication
import sys, logging
from comic_viewer.ui.main_window import MainWindow
from comic_viewer.config import ensure_dirs, APP_NAME

def main():
    ensure_dirs()

    # === LOGGING GLOBAL ===
    logging.basicConfig(
        level=logging.DEBUG,  # mude para INFO se ficar muito verboso
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    )
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("msal").setLevel(logging.INFO)

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
