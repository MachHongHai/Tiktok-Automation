import sys

from PySide6.QtWidgets import QApplication

from autodub.core.logging_config import configure_app_logging
from autodub.desktop.ui import AutoDubDesktopApp


def main() -> None:
    configure_app_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Auto Dub Video Local")
    window = AutoDubDesktopApp()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
