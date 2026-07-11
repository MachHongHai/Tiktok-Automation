import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property string tone: "secondary"
    property bool compact: false

    implicitHeight: compact ? 36 : 42
    leftPadding: compact ? 12 : 18
    rightPadding: compact ? 12 : 18
    font.pixelSize: compact ? Theme.caption : Theme.body
    font.weight: Font.Medium
    activeFocusOnTab: true
    Accessible.name: text

    contentItem: Text {
        text: root.text
        color: !root.enabled ? Theme.textSubtle
            : root.tone === "primary" ? Theme.sidebar
            : root.tone === "danger" ? Theme.danger
            : Theme.text
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: !root.enabled ? Theme.surfaceMuted
            : root.tone === "primary" ? (root.down ? "#3ca99a" : root.hovered ? Theme.interactiveHover : Theme.interactive)
            : root.tone === "ghost" ? (root.hovered ? Theme.surfaceMuted : "#00000000")
            : root.tone === "danger" ? (root.hovered ? Theme.dangerMuted : "#00000000")
            : root.down ? Theme.surfaceStrong
            : root.hovered ? Theme.surfaceMuted
            : Theme.surfaceElevated
        border.width: root.tone === "primary" || root.tone === "ghost" ? 0 : 1
        border.color: !root.enabled ? Theme.outline
            : root.tone === "danger" ? Theme.danger
            : root.activeFocus ? Theme.interactive : Theme.outline
    }
}
