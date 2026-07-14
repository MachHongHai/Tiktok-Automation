import QtQuick
import "."

Text {
    id: root

    property string glyph: ""
    property color iconColor: Theme.textMuted
    property int iconSize: Theme.icon

    text: glyph
    color: iconColor
    font.family: Theme.iconFont
    font.pixelSize: iconSize
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    textFormat: Text.PlainText
    Accessible.ignored: true
}
