import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string projectName
    required property string fileName
    required property string status
    required property int progress
    required property string thumbnailSource

    signal activated()

    width: 224
    height: 190
    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.interactive : Theme.outline
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: projectName

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

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: 9

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 112
            radius: Theme.radiusSmall
            color: Theme.surfaceElevated
            clip: true

            Image {
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: 448
                sourceSize.height: 224
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            Text {
                anchors.centerIn: parent
                visible: root.thumbnailSource.length === 0
                text: I18n.t("No preview")
                color: Theme.textSubtle
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
            }
        }

        Text {
            Layout.fillWidth: true
            text: root.projectName || root.fileName
            color: Theme.text
            font.pixelSize: Theme.body
            font.weight: Font.Medium
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        RowLayout {
            Layout.fillWidth: true

            Text {
                Layout.fillWidth: true
                text: root.status
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Text {
                text: qsTr("%1%").arg(root.progress)
                color: Theme.interactive
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                textFormat: Text.PlainText
            }
        }
    }
}
