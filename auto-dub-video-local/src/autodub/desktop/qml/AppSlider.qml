import QtQuick
import QtQuick.Controls.Basic
import "."

Slider {
    id: root

    implicitHeight: 28

    background: Rectangle {
        x: root.leftPadding
        y: root.topPadding + root.availableHeight / 2 - height / 2
        width: root.availableWidth
        height: 5
        radius: 3
        color: Theme.surfaceStrong

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: 3
            color: Theme.interactive
        }
    }

    handle: Rectangle {
        x: root.leftPadding + root.visualPosition * (root.availableWidth - width)
        y: root.topPadding + root.availableHeight / 2 - height / 2
        implicitWidth: 17
        implicitHeight: 17
        radius: 9
        color: root.pressed ? Theme.interactiveHover : Theme.text
        border.width: 3
        border.color: Theme.interactive
    }
}
