import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    property string label: ""
    property string value: ""

    spacing: 3

    Text {
        Layout.fillWidth: true
        text: root.label
        color: Theme.textMuted
        font.pixelSize: Theme.label
        font.weight: Font.Medium
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    Text {
        Layout.fillWidth: true
        text: root.value
        color: Theme.text
        font.pixelSize: Theme.h3
        fontSizeMode: Text.HorizontalFit
        minimumPixelSize: Theme.caption
        font.weight: Font.DemiBold
        textFormat: Text.PlainText
        elide: Text.ElideNone
    }
}
