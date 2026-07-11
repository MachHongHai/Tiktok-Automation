import QtQuick
import QtQuick.Controls.Basic
import "."

Rectangle {
    id: root

    property string text: ""
    property string emptyText: qsTr("No logs loaded.")

    radius: Theme.radiusSmall
    color: "#0c0e11"
    border.color: Theme.outline
    border.width: 1

    Flickable {
        id: flick

        property bool followTail: true
        property bool programmaticScroll: false

        anchors.fill: parent
        anchors.margins: 14
        clip: true
        contentWidth: width
        contentHeight: logText.paintedHeight

        function scrollToBottom() {
            programmaticScroll = true
            contentY = Math.max(0, contentHeight - height)
            programmaticScroll = false
        }

        onMovementStarted: followTail = false
        onContentYChanged: {
            if (!programmaticScroll) {
                followTail = contentY >= contentHeight - height - 8
            }
        }
        onContentHeightChanged: {
            if (followTail) {
                Qt.callLater(scrollToBottom)
            }
        }

        TextEdit {
            id: logText

            width: flick.width
            readOnly: true
            selectByMouse: true
            text: root.text || root.emptyText
            wrapMode: TextEdit.Wrap
            color: root.text ? "#cad3df" : Theme.textSubtle
            selectedTextColor: Theme.sidebar
            selectionColor: Theme.interactive
            font.family: "Cascadia Mono"
            font.pixelSize: 13
            textFormat: TextEdit.PlainText
        }

        ScrollBar.vertical: ScrollBar {}
    }
}
