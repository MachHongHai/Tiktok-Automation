import QtQuick
import QtQuick.Layouts
import "."

RowLayout {
    id: root

    property string title: ""
    property string subtitle: ""
    default property alias actions: actionArea.data

    spacing: 18

    ColumnLayout {
        Layout.fillWidth: true
        spacing: 5

        Text {
            Layout.fillWidth: true
            text: root.title
            color: Theme.text
            font.pixelSize: Theme.h1
            font.weight: Font.Medium
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        Text {
            Layout.fillWidth: true
            text: root.subtitle
            color: Theme.textMuted
            font.pixelSize: Theme.body
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
    }

    RowLayout {
        id: actionArea
        spacing: 10
    }
}
