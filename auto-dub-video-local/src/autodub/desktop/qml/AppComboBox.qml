pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import "."

ComboBox {
    id: root

    implicitHeight: 42
    leftPadding: 12
    rightPadding: 38
    font.pixelSize: Theme.body
    activeFocusOnTab: true
    Accessible.name: displayText

    Component.onCompleted: voicePopup.close()

    contentItem: Text {
        text: root.displayText
        color: root.enabled ? Theme.text : Theme.textDisabled
        font: root.font
        fontSizeMode: Text.HorizontalFit
        minimumPixelSize: Theme.label
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        elide: Text.ElideNone
    }

    indicator: AppIcon {
        x: root.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        width: Theme.icon
        height: Theme.icon
        glyph: root.popup.opened ? "\uE70E" : "\uE70D"
        iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
        iconSize: Theme.iconSmall
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.enabled && root.hovered ? Theme.surfaceMuted : Theme.input
        border.width: root.activeFocus || root.popup.opened ? 2 : 1
        border.color: root.activeFocus || root.popup.opened ? Theme.focus : Theme.outline

        Behavior on color {
            ColorAnimation { duration: Theme.motionFast }
        }
        Behavior on border.color {
            ColorAnimation { duration: Theme.motionFast }
        }
    }

    popup: Popup {
        id: voicePopup

        y: root.height + 6
        width: root.width
        height: Math.min(292, Math.max(52, voiceList.contentHeight + 12))
        padding: 6
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        onOpened: voiceList.currentIndex = root.highlightedIndex

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionFast }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
        }

        contentItem: ListView {
            id: voiceList

            clip: true
            model: root.delegateModel
            currentIndex: root.highlightedIndex
            reuseItems: true
            ScrollIndicator.vertical: ScrollIndicator {}
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outlineStrong
        }
    }

    delegate: ItemDelegate {
        id: voiceDelegate

        required property int index
        required property var modelData

        width: root.popup.width - 12
        height: 40
        highlighted: root.highlightedIndex === voiceDelegate.index

        contentItem: Text {
            text: root.textAt(voiceDelegate.index)
            color: voiceDelegate.highlighted ? Theme.interactive : Theme.text
            font.pixelSize: Theme.body
            fontSizeMode: Text.HorizontalFit
            minimumPixelSize: Theme.label
            font.weight: voiceDelegate.highlighted ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideNone
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: voiceDelegate.highlighted ? Theme.interactiveMuted : "transparent"
        }
    }
}
