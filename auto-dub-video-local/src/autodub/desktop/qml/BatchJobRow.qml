import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string fileName
    required property string status
    required property string step
    required property int progress
    required property string thumbnailSource

    signal activated()

    readonly property string statusLabel: status === "pending" ? qsTr("Queued")
        : status === "processing" ? qsTr("Processing")
        : status === "done" ? qsTr("Complete")
        : status === "failed" ? qsTr("Failed")
        : status === "cancelled" ? qsTr("Cancelled")
        : status

    width: ListView.view ? ListView.view.width : 640
    height: 92
    radius: Theme.radiusSmall
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surfaceElevated
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.interactive : Theme.outline
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: qsTr("Open job %1").arg(fileName)

    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        onTapped: {
            root.forceActiveFocus()
            root.activated()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 12
        spacing: 14

        Rectangle {
            Layout.preferredWidth: 112
            Layout.preferredHeight: 64
            radius: Theme.radiusSmall
            color: "#090a0c"
            border.width: 1
            border.color: Theme.outline
            clip: true

            Image {
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: 224
                sourceSize.height: 128
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            Text {
                anchors.centerIn: parent
                visible: root.thumbnailSource.length === 0
                text: "▶"
                color: Theme.textMuted
                font.pixelSize: Theme.h2
                textFormat: Text.PlainText
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 6

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.Medium
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: root.step.replace(/_/g, " ")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 210
            spacing: 8

            RowLayout {
                Layout.fillWidth: true

                StatusPill {
                    status: root.status
                    label: root.statusLabel
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("%1%").arg(root.progress)
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                }
            }

            AppProgressBar {
                Layout.fillWidth: true
                value: root.progress
            }
        }

        Text {
            text: ">"
            color: Theme.textSubtle
            font.pixelSize: Theme.body
            textFormat: Text.PlainText
        }
    }
}
