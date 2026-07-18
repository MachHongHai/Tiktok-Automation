import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ListView {
    id: root

    clip: true
    spacing: Theme.space8
    model: AppController.taskModel
    reuseItems: true

    delegate: Rectangle {
        id: taskDelegate

        required property string name
        required property string key
        required property string taskState
        required property string detail

        width: ListView.view.width
        height: 58
        radius: Theme.radiusSmall
        color: taskDelegate.taskState === "active" ? Theme.blueMuted : Theme.surfaceElevated
        border.width: 1
        border.color: taskDelegate.taskState === "active" ? Theme.blue : Theme.outline

        RowLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: Theme.space12

            Rectangle {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                radius: 14
                color: taskDelegate.taskState === "done" ? Theme.successMuted
                    : taskDelegate.taskState === "failed" ? Theme.dangerMuted
                    : taskDelegate.taskState === "active" ? Theme.blueMuted
                    : Theme.surfaceMuted

                AppIcon {
                    anchors.centerIn: parent
                    width: 16
                    height: 16
                    glyph: taskDelegate.taskState === "done" ? "\uE73E"
                        : taskDelegate.taskState === "failed" ? "\uEA39"
                        : taskDelegate.taskState === "cancelled" ? "\uE711"
                        : taskDelegate.taskState === "active" ? "\uE895"
                        : ""
                    iconColor: taskDelegate.taskState === "done" ? Theme.success
                        : taskDelegate.taskState === "failed" ? Theme.danger
                        : taskDelegate.taskState === "active" ? Theme.blue
                        : Theme.textMuted
                    iconSize: Theme.iconSmall
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t(taskDelegate.name)
                    color: Theme.text
                    font.pixelSize: Theme.body
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.stageLabel(taskDelegate.key)
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
            }

            StatusPill {
                status: taskDelegate.taskState
                label: I18n.taskStateLabel(taskDelegate.taskState)
            }
        }
    }

    ScrollBar.vertical: ScrollBar {}
}
