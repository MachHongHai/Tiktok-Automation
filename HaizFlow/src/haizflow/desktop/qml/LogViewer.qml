import QtQuick
import QtQuick.Controls.Basic
import "."

Rectangle {
    id: root

    property string text: ""
    property string emptyText: I18n.t("No logs loaded.")

    radius: Theme.radiusSmall
    color: Theme.codeSurface
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
        contentHeight: Math.max(height, logText.paintedHeight)
        boundsBehavior: Flickable.StopAtBounds

        function scrollToBottom() {
            programmaticScroll = true
            contentY = Math.max(0, contentHeight - height)
            programmaticScroll = false
        }

        onMovementStarted: followTail = false
        onContentYChanged: {
            if (!programmaticScroll)
                followTail = contentY >= contentHeight - height - 8
        }
        onContentHeightChanged: {
            if (followTail)
                Qt.callLater(scrollToBottom)
        }

        TextEdit {
            id: logText

            width: flick.width
            readOnly: true
            selectByMouse: true
            text: root.text || root.emptyText
            wrapMode: TextEdit.Wrap
            color: root.text ? Theme.codeText : Theme.textSubtle
            selectedTextColor: Theme.textOnAccent
            selectionColor: Theme.interactive
            font.family: "Cascadia Mono"
            font.pixelSize: 12
            textFormat: TextEdit.PlainText
        }

        ScrollBar.vertical: ScrollBar {
            policy: ScrollBar.AsNeeded
        }
    }
}
