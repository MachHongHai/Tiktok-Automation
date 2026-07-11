import QtQuick
import "."

Item {
    id: root

    property int xPercent: controller.subtitleX
    property int yPercent: controller.subtitleY
    property int boxWidthPercent: controller.subtitleBoxWidth
    property int boxHeightPercent: controller.subtitleBoxHeight
    property int storedFontSize: controller.subtitleFontSize
    property string mode: ""
    property real originMouseX: 0
    property real originMouseY: 0
    property int originXPercent: 50
    property int originYPercent: 88
    property int originWidthPercent: 72
    property int originHeightPercent: 12

    signal edited(int xPercent, int yPercent, int widthPercent, int heightPercent, int fontSize)

    function resetFromController() {
        xPercent = controller.subtitleX
        yPercent = controller.subtitleY
        boxWidthPercent = controller.subtitleBoxWidth
        boxHeightPercent = controller.subtitleBoxHeight
        storedFontSize = controller.subtitleFontSize
    }

    function edgeAt(localX, localY) {
        var threshold = 12
        if (localX <= threshold) {
            return "left"
        }
        if (width - localX <= threshold) {
            return "right"
        }
        if (localY <= threshold) {
            return "top"
        }
        if (height - localY <= threshold) {
            return "bottom"
        }
        return "move"
    }

    function emitEdit() {
        var fontSize = Math.max(10, Math.min(160, Math.round(Math.min(boxHeightPercent * 6, boxWidthPercent * 1.5))))
        storedFontSize = fontSize
        edited(Math.round(xPercent), Math.round(yPercent), Math.round(boxWidthPercent), Math.round(boxHeightPercent), fontSize)
    }

    width: parent ? Math.max(100, parent.width * boxWidthPercent / 100) : 100
    height: parent ? Math.max(42, parent.height * boxHeightPercent / 100) : 42
    x: parent ? Math.max(0, Math.min(parent.width - width, parent.width * xPercent / 100 - width / 2)) : 0
    y: parent ? Math.max(0, Math.min(parent.height - height, parent.height * yPercent / 100 - height / 2)) : 0
    visible: controller.previewInteractive

    Rectangle {
        anchors.fill: parent
        color: "#99121417"
        border.width: 2
        border.color: Theme.interactive
        radius: Theme.radiusSmall
    }

    Text {
        anchors.fill: parent
        anchors.margins: 5
        text: qsTr("Subtitle preview")
        color: "#ffffff"
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        font.pixelSize: 160
        fontSizeMode: Text.Fit
        minimumPixelSize: 12
        font.weight: Font.Bold
        textFormat: Text.PlainText
    }

    MouseArea {
        id: dragArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: {
            var edge = root.edgeAt(mouseX, mouseY)
            if (edge === "left" || edge === "right") {
                return Qt.SizeHorCursor
            }
            if (edge === "top" || edge === "bottom") {
                return Qt.SizeVerCursor
            }
            return Qt.SizeAllCursor
        }

        onPressed: function(mouse) {
            root.mode = root.edgeAt(mouse.x, mouse.y)
            root.originMouseX = mapToItem(root.parent, mouse.x, mouse.y).x
            root.originMouseY = mapToItem(root.parent, mouse.x, mouse.y).y
            root.originXPercent = root.xPercent
            root.originYPercent = root.yPercent
            root.originWidthPercent = root.boxWidthPercent
            root.originHeightPercent = root.boxHeightPercent
        }

        onPositionChanged: function(mouse) {
            if (!pressed || !root.parent) {
                return
            }
            var mapped = mapToItem(root.parent, mouse.x, mouse.y)
            var dxPercent = (mapped.x - root.originMouseX) * 100 / root.parent.width
            var dyPercent = (mapped.y - root.originMouseY) * 100 / root.parent.height
            if (root.mode === "move") {
                root.xPercent = Math.max(root.boxWidthPercent / 2, Math.min(100 - root.boxWidthPercent / 2, root.originXPercent + dxPercent))
                root.yPercent = Math.max(root.boxHeightPercent / 2, Math.min(100 - root.boxHeightPercent / 2, root.originYPercent + dyPercent))
            } else if (root.mode === "left") {
                var nextLeft = root.originXPercent - root.originWidthPercent / 2 + dxPercent
                var right = root.originXPercent + root.originWidthPercent / 2
                root.boxWidthPercent = Math.max(20, Math.min(95, right - nextLeft))
                root.xPercent = right - root.boxWidthPercent / 2
            } else if (root.mode === "right") {
                var left = root.originXPercent - root.originWidthPercent / 2
                var nextRight = root.originXPercent + root.originWidthPercent / 2 + dxPercent
                root.boxWidthPercent = Math.max(20, Math.min(95, nextRight - left))
                root.xPercent = left + root.boxWidthPercent / 2
            } else if (root.mode === "top") {
                var nextTop = root.originYPercent - root.originHeightPercent / 2 + dyPercent
                var bottom = root.originYPercent + root.originHeightPercent / 2
                root.boxHeightPercent = Math.max(6, Math.min(35, bottom - nextTop))
                root.yPercent = bottom - root.boxHeightPercent / 2
            } else if (root.mode === "bottom") {
                var top = root.originYPercent - root.originHeightPercent / 2
                var nextBottom = root.originYPercent + root.originHeightPercent / 2 + dyPercent
                root.boxHeightPercent = Math.max(6, Math.min(35, nextBottom - top))
                root.yPercent = top + root.boxHeightPercent / 2
            }
            root.emitEdit()
        }
    }
}
