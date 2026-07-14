import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    objectName: "settingsDialog"

    modal: true
    focus: true
    width: Math.min(640, parent ? parent.width - 48 : 640)
    height: 390
    padding: 0
    title: I18n.t("Settings")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

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

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
            NumberAnimation { property: "scale"; from: 1; to: 0.99; duration: Theme.motionFast }
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 68
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Settings")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Appearance and language")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space24
            spacing: Theme.space20

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space24

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Theme")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Choose the application appearance")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }

                SegmentedControl {
                    Layout.preferredWidth: 260
                    currentValue: root.draftTheme
                    options: [
                        { "label": I18n.t("Dark"), "value": "dark" },
                        { "label": I18n.t("Light"), "value": "light" }
                    ]
                    onActivated: function(value) {
                        root.draftTheme = value
                    }
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space24

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Language")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Choose the interface language")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }

                SegmentedControl {
                    Layout.preferredWidth: 260
                    currentValue: root.draftLanguage
                    options: [
                        { "label": I18n.t("English"), "value": "en" },
                        { "label": I18n.t("Vietnamese"), "value": "vi" }
                    ]
                    onActivated: function(value) {
                        root.draftLanguage = value
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                AppButton {
                    text: I18n.t("Reset defaults")
                    iconGlyph: "\uE777"
                    tone: "ghost"
                    onClicked: controller.resetSettings()
                }

                Item { Layout.fillWidth: true }

                AppButton {
                    text: I18n.t("Cancel")
                    tone: "ghost"
                    onClicked: root.close()
                }

                AppButton {
                    text: I18n.t("Apply settings")
                    iconGlyph: "\uE73E"
                    tone: "primary"
                    enabled: root.draftTheme !== controller.settingsTheme
                        || root.draftLanguage !== controller.settingsLanguage
                    onClicked: {
                        controller.applySettings(root.draftTheme, root.draftLanguage)
                        root.close()
                    }
                }
            }
        }
    }
}
