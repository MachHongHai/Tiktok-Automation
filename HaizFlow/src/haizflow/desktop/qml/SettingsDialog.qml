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
    height: Math.min(650, parent ? parent.height - 48 : 650)
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
    property string draftDevice: controller.processingDevice
    readonly property var hardwareInfo: controller.hardwareInfo

    onOpened: {
        draftTheme = controller.settingsTheme
        draftLanguage = controller.settingsLanguage
        draftDevice = controller.processingDevice
    }

    Connections {
        target: controller

        function onSettingsChanged() {
            root.draftTheme = controller.settingsTheme
            root.draftLanguage = controller.settingsLanguage
            root.draftDevice = controller.processingDevice
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
                    text: I18n.t("Appearance, language and performance")
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

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.divider
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space24

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 3

                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("Processing device")
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.draftDevice === "gpu" ? I18n.t("GPU processing") : I18n.t("CPU processing")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }
                    }

                    SegmentedControl {
                        Layout.preferredWidth: 260
                        currentValue: root.draftDevice
                        options: [
                            { "label": I18n.t("GPU"), "value": "gpu" },
                            { "label": I18n.t("CPU"), "value": "cpu" }
                        ]
                        onActivated: function(value) {
                            root.draftDevice = value
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    Layout.preferredHeight: visible ? implicitHeight : 0
                    text: root.hardwareInfo
                        ? controller.processingDeviceStatus(root.draftDevice)
                        : ""
                    visible: root.hardwareInfo && !controller.processingDeviceCompatible(root.draftDevice)
                    color: root.hardwareInfo && controller.processingDeviceCompatible(root.draftDevice)
                        ? Theme.textMuted
                        : Theme.danger
                    font.pixelSize: Theme.caption
                    wrapMode: Text.Wrap
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Recommended") + ": " + (root.hardwareInfo.recommendedDevice === "gpu"
                        ? I18n.t("GPU")
                        : I18n.t("CPU"))
                    color: root.hardwareInfo.recommendedDevice === "gpu" ? Theme.success : Theme.warning
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("GPU available") + ": " + (root.hardwareInfo.gpuSafe
                        ? root.hardwareInfo.availableGpuName
                        : I18n.t("No"))
                    color: root.hardwareInfo.gpuSafe ? Theme.success : Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 206
                radius: Theme.radiusSmall
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outline

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space16
                    spacing: Theme.space12

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Current hardware")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Active GPU") + "  " + (root.hardwareInfo.activeGpuName || I18n.t("Not available"))
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("CPU") + "  " + root.hardwareInfo.cpuName
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        elide: Text.ElideRight
                        textFormat: Text.PlainText
                    }

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        columnSpacing: Theme.space24
                        rowSpacing: Theme.space8

                        Text {
                            text: I18n.t("Total VRAM") + "  " + root.hardwareInfo.totalVram
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: I18n.t("Free VRAM") + "  " + root.hardwareInfo.freeVram
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: I18n.t("System RAM") + "  " + root.hardwareInfo.systemRam
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: I18n.t("CPU") + "  " + (root.hardwareInfo.cpuPhysicalCores || "--") + " " + I18n.t("cores")
                                + " / " + root.hardwareInfo.logicalCpuCount + " " + I18n.t("threads")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: I18n.t("Power source") + "  " + (root.hardwareInfo.acPowered === true
                                ? I18n.t("Plugged in")
                                : root.hardwareInfo.acPowered === false
                                    ? I18n.t("On battery") + (root.hardwareInfo.batteryPercent >= 0
                                        ? " (" + root.hardwareInfo.batteryPercent + "%)"
                                        : "")
                                    : I18n.t("Unknown"))
                            color: root.hardwareInfo.acPowered === false ? Theme.warning : Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: I18n.t("CPU clock") + "  " + (root.hardwareInfo.cpuMaxMhz > 0
                                ? (root.hardwareInfo.cpuMaxMhz / 1000).toFixed(1) + " GHz"
                                : "--")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }
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
                    enabled: (root.draftTheme !== controller.settingsTheme
                        || root.draftLanguage !== controller.settingsLanguage
                        || root.draftDevice !== controller.processingDevice)
                    onClicked: {
                        controller.applySettings(root.draftTheme, root.draftLanguage, root.draftDevice)
                    }
                }
            }
        }
    }
}
