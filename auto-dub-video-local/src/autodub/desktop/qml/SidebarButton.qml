import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property bool selected: false
    property string marker: ""

    implicitHeight: 46
    leftPadding: 14
    rightPadding: 12
    font.pixelSize: Theme.body
    font.weight: selected ? Font.Medium : Font.Normal
    activeFocusOnTab: true

    contentItem: Row {
        spacing: 11

        Rectangle {
            width: 26
            height: 26
            radius: 6
            color: root.selected ? Theme.interactiveMuted : Theme.sidebarMuted

            Text {
                anchors.centerIn: parent
                text: root.marker
                color: root.selected ? Theme.interactive : Theme.textOnDarkMuted
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
        }

        Text {
            width: Math.max(0, root.width - 65)
            height: 26
            text: root.text
            color: root.selected ? Theme.textOnDark : Theme.textOnDarkMuted
            font: root.font
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.selected ? Theme.sidebarMuted : root.hovered ? "#14171c" : "#00000000"
        border.width: root.activeFocus ? 1 : 0
        border.color: Theme.interactive

        Rectangle {
            width: 3
            height: 22
            radius: 2
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            color: Theme.interactive
            visible: root.selected
        }
    }
}
