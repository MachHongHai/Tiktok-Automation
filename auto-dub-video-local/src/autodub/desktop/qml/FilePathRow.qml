import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string label: ""
    property string path: ""

    spacing: 10

    Text {
        Layout.preferredWidth: 92
        text: root.label
        color: Theme.textMuted
        font.pixelSize: Theme.caption
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    Text {
        Layout.fillWidth: true
        text: root.path || I18n.t("Not available")
        color: root.path ? Theme.text : Theme.textMuted
        font.pixelSize: Theme.caption
        textFormat: Text.PlainText
        elide: Text.ElideMiddle
    }
}
