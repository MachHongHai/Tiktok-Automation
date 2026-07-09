from autodub.core.logging_config import configure_app_logging
from autodub.desktop.ui import AutoDubDesktopApp


def main() -> None:
    configure_app_logging()
    app = AutoDubDesktopApp()
    app.mainloop()


if __name__ == "__main__":
    main()

