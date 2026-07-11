import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtQml import QQmlApplicationEngine

from autodub.core.logging_config import configure_app_logging
from autodub.desktop.qml_controller import AutoDubController


def main() -> None:
    configure_app_logging()
    app = QApplication(sys.argv)
    app.setApplicationName("Video Dubbing")
    controller = AutoDubController()
    engine = QQmlApplicationEngine()
    qml_dir = Path(__file__).resolve().parent / "qml"
    engine.addImportPath(str(qml_dir))
    engine.rootContext().setContextProperty("controller", controller)
    engine.load(str(qml_dir / "Main.qml"))
    if not engine.rootObjects():
        controller.shutdown()
        raise SystemExit(1)
    exit_code = app.exec()
    controller.shutdown()
    del engine
    del controller
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
