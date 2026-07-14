import QtQuick
import QtQuick.Controls.Basic
import "."

MenuItem {
    id: root

    property string iconGlyph: ""
    property string tone: "normal"

    implicitWidth: 230
    implicitHeight: 40
    leftPadding: 11
    rightPadding: 11
    activeFocusOnTab: true
    Accessible.name: text

    contentItem: Item {
        Row {
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            spacing: 10

            AppIcon {
                width: Theme.icon
                height: 22
                glyph: root.iconGlyph
                iconColor: !root.enabled ? Theme.textDisabled
                    : root.tone === "danger" ? Theme.danger
                    : Theme.textMuted
                iconSize: Theme.iconSmall
            }

            Text {
                height: 22
                text: root.text
                color: !root.enabled ? Theme.textDisabled
                    : root.tone === "danger" ? Theme.danger
                    : Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
                elide: Text.ElideNone
            }
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.highlighted ? (root.tone === "danger" ? Theme.dangerMuted : Theme.surfaceMuted) : "transparent"

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
    }
}
