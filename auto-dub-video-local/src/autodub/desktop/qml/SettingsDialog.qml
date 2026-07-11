import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    modal: true
    focus: true
    width: 620
    padding: 22
    title: I18n.t("Settings")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)

    property string draftTheme: controller.settingsTheme
    property string draftLanguage: controller.settingsLanguage

    onOpened: {
        draftTheme = controller.settingsTheme
        draftLanguage = controller.settingsLanguage
    }

    Connections {
        target: controller

        function onSettingsChanged() {
            root.draftTheme = controller.settingsTheme
            root.draftLanguage = controller.settingsLanguage
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 18

        GridLayout {
            Layout.fillWidth: true
            columns: 2
            columnSpacing: 24
            rowSpacing: 18

            Text {
                text: I18n.t("Theme")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }

            AppComboBox {
                Layout.fillWidth: true
                textRole: "label"
                valueRole: "value"
                model: [
                    { "label": I18n.t("Dark"), "value": "dark" },
                    { "label": I18n.t("Light"), "value": "light" }
                ]
                currentIndex: root.draftTheme === "light" ? 1 : 0
                onActivated: root.draftTheme = currentValue
            }

            Text {
                text: I18n.t("Language")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }

            AppComboBox {
                Layout.fillWidth: true
                textRole: "label"
                valueRole: "value"
                model: [
                    { "label": I18n.t("English"), "value": "en" },
                    { "label": I18n.t("Vietnamese"), "value": "vi" }
                ]
                currentIndex: root.draftLanguage === "vi" ? 1 : 0
                onActivated: root.draftLanguage = currentValue
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 12

            AppButton {
                Layout.preferredWidth: 210
                text: I18n.t("Reset defaults")
                tone: "ghost"
                onClicked: controller.resetSettings()
            }

            Item { Layout.fillWidth: true }

            AppButton {
                Layout.preferredWidth: 96
                text: I18n.t("Close")
                onClicked: root.close()
            }

            AppButton {
                Layout.preferredWidth: 170
                text: I18n.t("Apply settings")
                tone: "primary"
                onClicked: controller.applySettings(root.draftTheme, root.draftLanguage)
            }
        }
    }
}
