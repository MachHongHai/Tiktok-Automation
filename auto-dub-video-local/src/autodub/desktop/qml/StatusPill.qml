import QtQuick
import "."

Rectangle {
    id: root

    property string status: "pending"
    property string label: status

    readonly property color statusColor: status === "done" ? Theme.success
        : status === "failed" || status === "cancelled" ? Theme.danger
        : status === "processing" || status === "active" ? Theme.warning
        : status === "awaiting_review" ? Theme.blue
        : Theme.textMuted
    readonly property color statusBackground: status === "done" ? Theme.successMuted
        : status === "failed" || status === "cancelled" ? Theme.dangerMuted
        : status === "processing" || status === "active" ? Theme.warningMuted
        : status === "awaiting_review" ? Theme.blueMuted
        : Theme.surfaceMuted

    implicitWidth: content.implicitWidth + 20
    implicitHeight: 26
    radius: Theme.radiusSmall
    color: statusBackground
    border.width: 0

    Row {
        id: content
        anchors.centerIn: parent
        spacing: 7

        Rectangle {
            width: 6
            height: 6
            radius: 3
            anchors.verticalCenter: parent.verticalCenter
            color: root.statusColor
        }

        Text {
            text: root.label
            color: root.statusColor
            font.pixelSize: Theme.label
            font.weight: Font.DemiBold
            textFormat: Text.PlainText
        }
    }
}
