import QtQuick
import QtQuick.Controls.Basic
import "."

SpinBox {
    id: root

    implicitHeight: 42
    editable: true
    leftPadding: 38
    rightPadding: 38
    font.pixelSize: Theme.body
    activeFocusOnTab: true

    contentItem: TextInput {
        text: root.textFromValue(root.value, root.locale)
        color: root.enabled ? Theme.text : Theme.textDisabled
        font: root.font
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        readOnly: !root.editable
        validator: root.validator
        inputMethodHints: Qt.ImhFormattedNumbersOnly
        selectByMouse: true
    }

    down.indicator: Rectangle {
        x: 1
        y: 1
        width: 36
        height: root.height - 2
        color: root.down.pressed ? Theme.interactiveMuted : "transparent"

        AppIcon {
            anchors.centerIn: parent
            width: 16
            height: 16
            glyph: "\uE738"
            iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
            iconSize: Theme.iconSmall
        }
    }

    up.indicator: Rectangle {
        x: root.width - width - 1
        y: 1
        width: 36
        height: root.height - 2
        color: root.up.pressed ? Theme.interactiveMuted : "transparent"

        AppIcon {
            anchors.centerIn: parent
            width: 16
            height: 16
            glyph: "\uE710"
            iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
            iconSize: Theme.iconSmall
        }
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.input
        border.width: root.activeFocus ? 2 : 1
        border.color: root.activeFocus ? Theme.focus : Theme.outline
    }
}
