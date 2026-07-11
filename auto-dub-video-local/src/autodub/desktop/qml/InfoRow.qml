import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string label: ""
    property string value: ""

    spacing: 12

    Text {
        Layout.fillWidth: true
        text: root.label
        color: Theme.textMuted
        font.pixelSize: Theme.caption
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    Text {
        Layout.maximumWidth: 220
        text: root.value
        color: Theme.text
        font.pixelSize: Theme.caption
        font.weight: Font.Medium
        horizontalAlignment: Text.AlignRight
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }
}
