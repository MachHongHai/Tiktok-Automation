import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    objectName: "projectSetupDialog"

    modal: true
    focus: true
    width: Math.min(620, parent ? parent.width - 48 : 620)
    height: 346
    padding: 0
    title: root.projectType === "batch"
        ? I18n.t("Create batch project")
        : I18n.t("Create single project")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null
    property string projectType: "single"

    function openForType(type) {
        projectType = type === "batch" ? "batch" : "single"
        open()
    }

    onOpened: {
        projectName.clear()
        projectName.forceActiveFocus()
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
            Layout.preferredHeight: 64
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: root.title
                color: Theme.text
                font.pixelSize: Theme.h2
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
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
            spacing: Theme.space16

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    text: I18n.t("Project name")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }

                TextField {
                    id: projectName
                    objectName: "projectNameInput"
                    Layout.fillWidth: true
                    implicitHeight: 44
                    color: Theme.text
                    font.pixelSize: Theme.body
                    selectByMouse: true
                    activeFocusOnTab: true
                    Accessible.name: I18n.t("Project name")
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: Theme.input
                        border.width: projectName.activeFocus ? 2 : 1
                        border.color: projectName.activeFocus ? Theme.focus : Theme.outline
                    }
                    Keys.onReturnPressed: {
                        if (continueButton.enabled)
                            continueButton.clicked()
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    text: I18n.t("Project storage location")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        radius: Theme.radiusSmall
                        color: Theme.input
                        border.width: 1
                        border.color: Theme.outline

                        Text {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            text: controller.projectDirectory
                            color: Theme.text
                            font.pixelSize: Theme.caption
                            verticalAlignment: Text.AlignVCenter
                            textFormat: Text.PlainText
                            elide: Text.ElideMiddle
                        }
                    }

                    AppButton {
                        text: I18n.t("Browse")
                        iconGlyph: "\uE8B7"
                        onClicked: controller.browseProjectDirectory()
                    }
                }
            }

            Item {
                Layout.fillHeight: true
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Item { Layout.fillWidth: true }

                AppButton {
                    text: I18n.t("Cancel")
                    tone: "ghost"
                    onClicked: root.close()
                }

                AppButton {
                    id: continueButton
                    objectName: "continueProjectButton"
                    text: I18n.t("Continue")
                    iconGlyph: "\uE76C"
                    tone: "primary"
                    enabled: projectName.text.trim().length > 0 && controller.projectDirectory.length > 0
                    onClicked: {
                        if (controller.prepareProject(projectName.text.trim(), controller.projectDirectory, root.projectType))
                            root.close()
                    }
                }
            }
        }
    }
}
