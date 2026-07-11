import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property alias title: titleLabel.text
    property alias subtitle: subtitleLabel.text
    property bool headerVisible: title.length > 0 || subtitle.length > 0
    default property alias content: body.data

    color: Theme.surface
    radius: Theme.radius
    border.color: Theme.outline
    border.width: 1
    implicitHeight: column.implicitHeight + 36

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: 18
        spacing: 16

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 4
            visible: root.headerVisible

            Text {
                id: titleLabel
                Layout.fillWidth: true
                color: Theme.text
                font.pixelSize: Theme.h2
                font.weight: Font.Medium
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Text {
                id: subtitleLabel
                Layout.fillWidth: true
                visible: text.length > 0
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                wrapMode: Text.WordWrap
            }
        }

        ColumnLayout {
            id: body
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 12
        }
    }
}
