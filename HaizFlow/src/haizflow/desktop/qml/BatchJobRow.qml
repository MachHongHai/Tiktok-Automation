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

    readonly property string statusLabel: status === "pending" ? I18n.t("Queued")
        : status === "processing" ? I18n.t("Processing")
        : status === "done" ? I18n.t("Complete")
        : status === "failed" ? I18n.t("Failed")
        : status === "cancelled" ? I18n.t("Cancelled")
        : status === "paused" ? I18n.t("Paused")
        : status === "awaiting_review" ? I18n.t("Review needed")
        : I18n.taskStateLabel(status)

    width: ListView.view ? ListView.view.width : 640
    height: 82
    radius: Theme.radiusSmall
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surfaceElevated
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : Theme.outline
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: I18n.t("Open video") + " " + fileName
    scale: tapHandler.pressed ? 0.995 : 1

    Keys.onReturnPressed: root.activated()
    Keys.onSpacePressed: root.activated()

    HoverHandler {
        id: hoverHandler
        cursorShape: Qt.PointingHandCursor
    }

    TapHandler {
        id: tapHandler
        onTapped: {
            root.forceActiveFocus()
            root.activated()
        }
    }

    RowLayout {
        anchors.fill: parent
        anchors.margins: 10
        spacing: Theme.space12

        Rectangle {
            Layout.preferredWidth: 96
            Layout.preferredHeight: 58
            radius: Theme.radiusSmall
            color: Theme.video
            clip: true

            Image {
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: 192
                sourceSize.height: 116
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            AppIcon {
                anchors.centerIn: parent
                visible: root.thumbnailSource.length === 0
                width: 24
                height: 24
                glyph: "\uE714"
                iconColor: Theme.textSubtle
                iconSize: Theme.icon
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 5

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            Text {
                Layout.fillWidth: true
                text: I18n.stageLabel(root.step)
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 230
            spacing: Theme.space8

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
                    font.weight: Font.DemiBold
                    horizontalAlignment: Text.AlignRight
                    textFormat: Text.PlainText
                }
            }

            AppProgressBar {
                Layout.fillWidth: true
                value: root.progress
            }
        }

        AppIcon {
            Layout.preferredWidth: Theme.icon
            Layout.preferredHeight: Theme.icon
            glyph: "\uE76C"
            iconColor: hoverHandler.hovered ? Theme.text : Theme.textSubtle
            iconSize: Theme.iconSmall
        }
    }

    transform: Translate {
        x: hoverHandler.hovered ? 2 : 0
        Behavior on x {
            NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
        }
    }
    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on scale {
        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
    }
}
