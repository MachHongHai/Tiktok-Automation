import os
import sys
import unittest
from pathlib import Path


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlEngine


ROOT = Path(__file__).resolve().parents[1]
QML_DIR = ROOT / "src" / "haizflow" / "desktop" / "qml"


class QmlMenuTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QGuiApplication.instance() or QGuiApplication([])

    def test_menu_item_keeps_its_label_after_repeated_visibility_changes(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine, QUrl.fromLocalFile(str(QML_DIR / "AppMenuItem.qml")))
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        item = component.createWithInitialProperties({"text": "Open project folder", "visible": True})
        self.assertIsNotNone(item, "\n".join(error.toString() for error in component.errors()))
        try:
            label = item.findChild(QObject, "menuItemLabel")
            self.assertIsNotNone(label)
            for visible in (False, True, False, True):
                item.setProperty("visible", visible)
                self.app.processEvents()
            self.assertEqual(label.property("text"), "Open project folder")
            self.assertGreater(label.property("implicitWidth"), 0)
            self.assertGreater(label.property("implicitHeight"), 0)
            item.setProperty("visible", False)
            self.app.processEvents()
            self.assertEqual(item.property("implicitWidth"), 0)
            self.assertEqual(item.property("implicitHeight"), 0)
        finally:
            item.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_open_menu_keeps_every_visible_item_label(self):
        engine = QQmlEngine()
        component = QQmlComponent(engine)
        qml_directory = QML_DIR.as_uri()
        component.setData(
            f'''import QtQuick
import QtQuick.Controls.Basic
import "{qml_directory}"

ApplicationWindow {{
    width: 360
    height: 240
    visible: true

    Menu {{
        id: actionMenu
        objectName: "actionMenu"
        parent: Overlay.overlay
        AppMenuItem {{ objectName: "sourceAction"; text: "Open source video"; iconGlyph: "\\uE714" }}
        AppMenuItem {{ objectName: "projectAction"; text: "Open project folder"; iconGlyph: "\\uE8B7" }}
        AppMenuItem {{ objectName: "deleteAction"; text: "Delete project"; tone: "danger"; iconGlyph: "\\uE74D" }}
    }}

    Component.onCompleted: actionMenu.open()
}}'''.encode("utf-8"),
            QUrl(),
        )
        self.assertTrue(component.isReady(), "\n".join(error.toString() for error in component.errors()))
        window = component.create()
        self.assertIsNotNone(window, "\n".join(error.toString() for error in component.errors()))
        try:
            for _ in range(3):
                self.app.processEvents()
            menu = window.findChild(QObject, "actionMenu")
            self.assertTrue(menu.property("visible"))
            for action_name, expected_text in (
                ("sourceAction", "Open source video"),
                ("projectAction", "Open project folder"),
                ("deleteAction", "Delete project"),
            ):
                action = window.findChild(QObject, action_name)
                self.assertIsNotNone(action)
                label = action.findChild(QObject, "menuItemLabel")
                self.assertIsNotNone(label)
                self.assertEqual(label.property("text"), expected_text)
                self.assertGreater(label.property("width"), 0)
        finally:
            window.close()
            window.deleteLater()
            engine.deleteLater()
            self.app.processEvents()

    def test_batch_video_menu_does_not_offer_project_deletion(self):
        command_bar = (QML_DIR / "VideoCommandBar.qml").read_text(encoding="utf-8")
        self.assertIn("visible: root.hasProject && !AppController.isSelectedBatchVideo", command_bar)


if __name__ == "__main__":
    unittest.main()
