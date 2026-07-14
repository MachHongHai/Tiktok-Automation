import QtQuick
import QtQuick.Controls.Basic
import "."

CheckBox {
    id: root

    spacing: 10
    font.pixelSize: Theme.body
    activeFocusOnTab: true
    Accessible.name: text

    indicator: Rectangle {
        implicitWidth: 20
        implicitHeight: 20
        x: root.leftPadding
        y: parent.height / 2 - height / 2
        radius: Theme.radiusTiny
        color: root.checked ? Theme.interactive : Theme.input
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus : root.checked ? Theme.interactive : Theme.outlineStrong

        AppIcon {
            anchors.centerIn: parent
            width: 14
            height: 14
            visible: root.checked
            glyph: "\uE73E"
            iconColor: Theme.textOnAccent
            iconSize: 12
        }

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
    }

    contentItem: Text {
        leftPadding: root.indicator.width + root.spacing
        text: root.text
        color: root.enabled ? Theme.text : Theme.textDisabled
        font: root.font
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        elide: Text.ElideNone
        wrapMode: Text.WordWrap
    }
}
