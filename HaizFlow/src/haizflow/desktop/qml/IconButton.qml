import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property string glyph: ""
    property string tone: "ghost"
    property string toolTipText: ""
    property int controlSize: 40

    implicitWidth: controlSize
    implicitHeight: controlSize
    activeFocusOnTab: true
    Accessible.name: toolTipText
    scale: down ? 0.96 : 1

    contentItem: AppIcon {
        glyph: root.glyph
        iconSize: Theme.icon
        iconColor: !root.enabled ? Theme.textDisabled
            : root.tone === "danger" ? Theme.danger
            : root.tone === "primary" ? Theme.textOnAccent
            : Theme.textMuted
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: !root.enabled ? "transparent"
            : root.tone === "primary" ? (root.down ? Theme.interactivePressed : root.hovered ? Theme.interactiveHover : Theme.interactive)
            : root.tone === "danger" && (root.hovered || root.down) ? Theme.dangerMuted
            : root.down ? Theme.surfaceStrong
            : root.hovered ? Theme.surfaceMuted
            : "transparent"
        border.width: root.activeFocus ? 2 : 0
        border.color: Theme.focus

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
    }

    Behavior on scale {
        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
    }

    ToolTip.visible: hovered && toolTipText.length > 0
    ToolTip.text: toolTipText
    ToolTip.delay: 450
}
