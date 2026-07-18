import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

MenuItem {
    id: root

    property string iconGlyph: ""
    property string tone: "normal"

    // Qt's Menu still consults implicit size for hidden entries. Collapse them
    // fully so conditional actions never leave an empty menu row behind.
    implicitWidth: visible ? 230 : 0
    implicitHeight: visible ? 40 : 0
    leftPadding: 11
    rightPadding: 11
    activeFocusOnTab: true
    Accessible.name: text

    contentItem: RowLayout {
        spacing: 10
        implicitWidth: menuIcon.implicitWidth + spacing + menuLabel.implicitWidth
        implicitHeight: Math.max(menuIcon.implicitHeight, menuLabel.implicitHeight)

        AppIcon {
            id: menuIcon
            Layout.preferredWidth: Theme.icon
            Layout.preferredHeight: 22
            glyph: root.iconGlyph
            iconColor: !root.enabled ? Theme.textDisabled
                : root.tone === "danger" ? Theme.danger
                : Theme.textMuted
            iconSize: Theme.iconSmall
        }

        Text {
            id: menuLabel
            objectName: "menuItemLabel"
            Layout.fillWidth: true
            Layout.preferredHeight: 22
            text: root.text
            color: !root.enabled ? Theme.textDisabled
                : root.tone === "danger" ? Theme.danger
                : Theme.text
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
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
