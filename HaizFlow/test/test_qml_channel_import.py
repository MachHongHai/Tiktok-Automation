import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, Property, QUrl, Slot
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
QML_DIR = SRC / "haizflow" / "desktop" / "qml"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from haizflow.desktop.channel_import import ChannelImportCoordinator


class _FakeController(QObject):
    def __init__(self):
        super().__init__()
        self._importer = ChannelImportCoordinator(self)

    @Property(QObject, constant=True)
    def channelImporter(self):
        return self._importer

    @Property(str, constant=True)
    def projectName(self):
        return "Channel test"

    @Slot(result=bool)
    def prepareChannelImport(self):
        return True

    @Slot(result=bool)
    def startChannelDownloads(self):
        return False

    @Slot(int, result=bool)
    def retryChannelVideo(self, _row):
        return False


class ChannelImportQmlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_channel_import_page_loads_with_an_empty_session(self):
        engine = QQmlEngine()
        engine.addImportPath(str(QML_DIR))
        controller = _FakeController()
        engine.rootContext().setContextProperty("controller", controller)
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "ChannelImportPage.qml")))
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        page = component.create()
        self.assertIsNotNone(page, "\n".join(error.toString() for error in component.errors()))
        try:
            self.app.processEvents()
            self.assertEqual(page.property("hasResults"), False)
        finally:
            controller._importer.shutdown()
            page.deleteLater()
            engine.deleteLater()
            self.app.processEvents()


if __name__ == "__main__":
    unittest.main()
