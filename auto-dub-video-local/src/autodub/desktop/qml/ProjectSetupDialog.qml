import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root

    modal: true
    focus: true
    width: 560
    padding: 22
    title: I18n.t("Create project")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    onOpened: {
        projectName.text = ""
        projectName.forceActiveFocus()
        projectName.selectAll()
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 16

        Text {
            text: I18n.t("Project name")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            textFormat: Text.PlainText
        }

        TextField {
            id: projectName
            objectName: "projectNameInput"
            Layout.fillWidth: true
            implicitHeight: 42
            color: Theme.text
            font.pixelSize: Theme.body
            selectByMouse: true
            background: Rectangle {
                radius: Theme.radiusSmall
                color: Theme.surfaceElevated
                border.width: 1
                border.color: projectName.activeFocus ? Theme.interactive : Theme.outline
            }
        }

        Text {
            text: I18n.t("Project folder")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            textFormat: Text.PlainText
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 10

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 42
                radius: Theme.radiusSmall
                color: Theme.surfaceElevated
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
                Layout.preferredWidth: 152
                text: I18n.t("Browse")
                onClicked: controller.browseProjectDirectory()
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.topMargin: 6
            spacing: 12

            Item { Layout.fillWidth: true }

            AppButton {
                Layout.preferredWidth: 100
                text: I18n.t("Cancel")
                tone: "ghost"
                onClicked: root.close()
            }

            AppButton {
                id: continueButton
                objectName: "continueProjectButton"
                Layout.preferredWidth: 150
                text: I18n.t("Continue")
                tone: "primary"
                // Bind to the live editor value, including every keystroke.
                enabled: projectName.text.trim().length > 0 && controller.projectDirectory.length > 0
                onClicked: {
                    if (controller.prepareProject(projectName.text.trim(), controller.projectDirectory))
                        root.close()
                }
            }
        }
    }
}
