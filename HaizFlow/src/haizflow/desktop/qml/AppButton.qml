import QtQuick
import QtQuick.Controls.Basic
import "."

Button {
    id: root

    property string tone: "secondary"
    property bool compact: false
    property string iconGlyph: ""
    property string toolTipText: ""

    implicitHeight: compact ? 34 : 42
    implicitWidth: Math.max(compact ? 72 : 92, buttonContent.implicitWidth + leftPadding + rightPadding)
    leftPadding: compact ? 12 : 16
    rightPadding: compact ? 12 : 16
    font.pixelSize: compact ? Theme.caption : Theme.body
    font.weight: Font.DemiBold
    activeFocusOnTab: true
    Accessible.name: text
    Accessible.description: toolTipText
    scale: down ? 0.98 : 1

    readonly property color foregroundColor: !enabled ? Theme.textDisabled
        : tone === "primary" ? Theme.textOnAccent
        : tone === "danger" ? Theme.danger
        : Theme.text

    contentItem: Item {
        implicitWidth: buttonContent.implicitWidth
        implicitHeight: Math.max(buttonContent.implicitHeight, Theme.icon)

        Row {
            id: buttonContent
            anchors.centerIn: parent
            spacing: root.iconGlyph.length > 0 && root.text.length > 0 ? 8 : 0

            AppIcon {
                width: root.iconGlyph.length > 0 ? Theme.icon : 0
                height: parent.height
                visible: root.iconGlyph.length > 0
                glyph: root.iconGlyph
                iconColor: root.foregroundColor
                iconSize: root.compact ? Theme.iconSmall : Theme.icon
            }

            Text {
                height: Math.max(20, implicitHeight)
                text: root.text
                color: root.foregroundColor
                font: root.font
                verticalAlignment: Text.AlignVCenter
                textFormat: Text.PlainText
                elide: Text.ElideNone
            }
        }
    }

    background: Rectangle {
        id: buttonBackground
        radius: Theme.radiusSmall
        color: !root.enabled ? Theme.surfaceMuted
            : root.tone === "primary" ? (root.down ? Theme.interactivePressed : root.hovered ? Theme.interactiveHover : Theme.interactive)
            : root.tone === "ghost" ? (root.down ? Theme.surfaceStrong : root.hovered ? Theme.surfaceMuted : "transparent")
            : root.tone === "danger" ? (root.down || root.hovered ? Theme.dangerMuted : "transparent")
            : root.down ? Theme.surfaceStrong
            : root.hovered ? Theme.surfaceMuted
            : Theme.surfaceElevated
        border.width: root.activeFocus ? 2 : root.tone === "primary" ? 0 : 1
        border.color: root.activeFocus ? Theme.focus
            : root.tone === "danger" ? Theme.danger
            : Theme.outline

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.motionFast }
        }
    }

    Behavior on scale {
        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
    }

    ToolTip.visible: hovered && toolTipText.length > 0
    ToolTip.text: toolTipText
    ToolTip.delay: 500
}
