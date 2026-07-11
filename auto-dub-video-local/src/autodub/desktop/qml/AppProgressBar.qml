import QtQuick
import QtQuick.Controls.Basic
import "."

ProgressBar {
    id: root

    implicitHeight: 7
    from: 0
    to: 100

    background: Rectangle {
        implicitHeight: 7
        radius: 4
        color: Theme.surfaceStrong
    }

    contentItem: Item {
        implicitHeight: 7

        Rectangle {
            width: root.visualPosition * parent.width
            height: parent.height
            radius: 4
            color: root.value >= root.to ? Theme.success : Theme.interactive
        }
    }
}
