import QtQuick
import "."

Rectangle {
    id: root

    property string status: "pending"
    property string label: status

    implicitWidth: content.implicitWidth + 24
    implicitHeight: 28
    radius: 6
    color: status === "done" ? Theme.successMuted
        : status === "failed" ? Theme.dangerMuted
        : status === "cancelled" ? Theme.surfaceMuted
        : status === "processing" || status === "active" ? Theme.warningMuted
        : Theme.surfaceElevated
    border.width: 1
    border.color: status === "done" ? "#28664f"
        : status === "failed" ? "#754038"
        : status === "processing" || status === "active" ? "#75602f"
        : Theme.outline

    Row {
        id: content
        anchors.centerIn: parent
        spacing: 7

        Rectangle {
            width: 7
            height: 7
            radius: 4
            anchors.verticalCenter: parent.verticalCenter
            color: root.status === "done" ? Theme.success
                : root.status === "failed" ? Theme.danger
                : root.status === "processing" || root.status === "active" ? Theme.warning
                : Theme.textSubtle
        }

        Text {
            text: root.label
            color: root.status === "done" ? Theme.success
                : root.status === "failed" ? Theme.danger
                : root.status === "processing" || root.status === "active" ? Theme.warning
                : Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }
    }
}
