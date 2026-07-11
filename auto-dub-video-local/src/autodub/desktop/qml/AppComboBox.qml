import QtQuick
import QtQuick.Controls.Basic
import "."

ComboBox {
    id: root

    implicitHeight: 42
    leftPadding: 12
    rightPadding: 34
    font.pixelSize: Theme.body
    activeFocusOnTab: true

    contentItem: Text {
        text: root.displayText
        color: Theme.text
        font: root.font
        verticalAlignment: Text.AlignVCenter
        textFormat: Text.PlainText
        elide: Text.ElideRight
    }

    indicator: Text {
        x: root.width - width - 12
        anchors.verticalCenter: parent.verticalCenter
        text: "v"
        color: Theme.textMuted
        font.pixelSize: Theme.caption
        textFormat: Text.PlainText
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.hovered ? Theme.surfaceStrong : Theme.surfaceElevated
        border.width: 1
        border.color: root.activeFocus ? Theme.interactive : Theme.outline
    }

    popup: Popup {
        y: root.height + 5
        width: root.width
        height: Math.min(280, contentItem.implicitHeight + 12)
        padding: 6
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
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
        width: root.width - 12
        height: 40
        highlighted: root.highlightedIndex === index

        contentItem: Text {
            text: {
                if (modelData === undefined || modelData === null) {
                    return ""
                }
                if (root.textRole && typeof modelData === "object") {
                    return modelData[root.textRole] || ""
                }
                return String(modelData)
            }
            color: highlighted ? Theme.interactive : Theme.text
            font.pixelSize: Theme.body
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: highlighted ? Theme.interactiveMuted : "#00000000"
        }
    }
}
