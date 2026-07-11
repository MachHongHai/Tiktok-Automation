import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

ListView {
    id: root

    clip: true
    spacing: 8
    model: controller.taskModel
    reuseItems: true

    delegate: Rectangle {
        required property string name
        required property string key
        required property string state
        required property string detail

        width: ListView.view.width
        height: 58
        radius: 8
        color: state === "active" ? "#eff6ff" : Theme.surface
        border.width: 1
        border.color: state === "active" ? "#bfdbfe" : Theme.outline

        RowLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 12

            Rectangle {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                radius: 14
                color: state === "done" ? Theme.success
                    : state === "failed" ? Theme.danger
                    : state === "cancelled" ? Theme.textMuted
                    : state === "active" ? Theme.interactive
                    : Theme.surfaceMuted
                border.width: state === "pending" ? 1 : 0
                border.color: Theme.outline

                Text {
                    anchors.centerIn: parent
                    text: state === "done" ? "OK" : state === "failed" ? "!" : state === "cancelled" ? "X" : state === "active" ? ">" : ""
                    color: "#ffffff"
                    font.pixelSize: Theme.body
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: name
                    color: Theme.text
                    font.pixelSize: Theme.body
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: detail
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
            }

            StatusPill {
                status: state
                label: state
            }
        }
    }

    ScrollBar.vertical: ScrollBar {}
}
