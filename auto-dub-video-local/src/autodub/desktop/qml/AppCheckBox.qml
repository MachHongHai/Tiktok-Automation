import QtQuick
import QtQuick.Controls.Basic
import "."

CheckBox {
    id: root

    spacing: 10
    font.pixelSize: Theme.body
    activeFocusOnTab: true

    indicator: Rectangle {
        implicitWidth: 20
        implicitHeight: 20
        x: root.leftPadding
        y: parent.height / 2 - height / 2
        radius: 5
        color: root.checked ? Theme.interactive : Theme.surfaceElevated
        border.width: 1
        border.color: root.checked ? Theme.interactive : root.activeFocus ? Theme.interactive : Theme.outlineStrong

        Text {
            anchors.centerIn: parent
            text: root.checked ? "x" : ""
            color: Theme.sidebar
            font.pixelSize: Theme.caption
            font.weight: Font.Bold
            textFormat: Text.PlainText
        }
    }

    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing
        text: root.text
        color: Theme.text
        font: root.font
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }
}
