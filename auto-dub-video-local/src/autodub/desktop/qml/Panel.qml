import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    property alias title: titleLabel.text
    property alias subtitle: subtitleLabel.text
    property bool headerVisible: title.length > 0 || subtitle.length > 0
    property int contentPadding: 20
    property int contentSpacing: 14
    property bool muted: false
    default property alias content: body.data

    color: muted ? Theme.surfaceElevated : Theme.surface
    radius: Theme.radius
    border.color: Theme.outline
    border.width: 1
    implicitHeight: column.implicitHeight + contentPadding * 2

    ColumnLayout {
        id: column
        anchors.fill: parent
        anchors.margins: root.contentPadding
        spacing: root.headerVisible ? Theme.space20 : 0

        ColumnLayout {
            Layout.fillWidth: true
            spacing: Theme.space4
            visible: root.headerVisible

            Text {
                id: titleLabel
                Layout.fillWidth: true
                color: Theme.text
                font.pixelSize: Theme.h3
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideNone
                wrapMode: Text.WordWrap
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
            spacing: root.contentSpacing
        }
    }
}
