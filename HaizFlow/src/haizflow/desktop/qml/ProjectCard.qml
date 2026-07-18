import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string projectName
    required property string projectType
    required property int videoCount
    required property string status
    required property int progress
    required property string thumbnailSource

    signal activated()

    readonly property string statusLabel: status === "pending" ? I18n.t("Queued")
        : status === "empty" ? I18n.t("No source selected")
        : status === "processing" ? I18n.t("Processing")
        : status === "done" ? I18n.t("Complete")
        : status === "failed" ? I18n.t("Failed")
        : status === "cancelled" ? I18n.t("Cancelled")
        : status === "paused" ? I18n.t("Paused")
        : status === "awaiting_review" ? I18n.t("Review needed")
        : I18n.taskStateLabel(status)
    readonly property color statusColor: status === "done" ? Theme.success
        : status === "failed" || status === "cancelled" ? Theme.danger
        : status === "processing" ? Theme.warning
        : status === "awaiting_review" ? Theme.blue
        : Theme.textMuted

    height: Math.round(width * 0.58 + 82)
    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : Theme.outline
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: projectName
    scale: tapHandler.pressed ? 0.99 : 1

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

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: Math.round(root.width * 0.56)
            radius: Theme.radius
            color: Theme.video
            clip: true

            Image {
                id: thumbnailImage
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: Math.round(root.width * 2)
                sourceSize.height: Math.round(root.width * 1.12)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready

                Behavior on opacity {
                    NumberAnimation { duration: Theme.motionStandard }
                }
            }

            ThumbnailFallback {
                anchors.fill: parent
                visible: root.thumbnailSource.length === 0 || thumbnailImage.status === Image.Error
            }

            Rectangle {
                anchors.top: parent.top
                anchors.left: parent.left
                anchors.margins: Theme.space8
                visible: root.projectType === "batch"
                implicitWidth: batchLabel.implicitWidth + 16
                implicitHeight: 24
                radius: Theme.radiusTiny
                color: Theme.surfaceStrong

                Text {
                    id: batchLabel
                    anchors.centerIn: parent
                    text: qsTr("%1 %2").arg(root.videoCount).arg(I18n.t("videos"))
                    color: Theme.text
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 3
                color: Theme.surfaceStrong

                Rectangle {
                    width: parent.width * Math.max(0, Math.min(100, root.progress)) / 100
                    height: parent.height
                    color: root.progress >= 100 ? Theme.success : Theme.interactive

                    Behavior on width {
                        NumberAnimation { duration: Theme.motionStandard; easing.type: Easing.OutCubic }
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: 14
            Layout.rightMargin: 14
            Layout.topMargin: 11
            Layout.bottomMargin: 11
            spacing: 7

            Text {
                Layout.fillWidth: true
                text: root.projectName
                color: Theme.text
                font.pixelSize: Theme.bodyLarge
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Rectangle {
                    Layout.preferredWidth: 7
                    Layout.preferredHeight: 7
                    radius: 4
                    color: root.statusColor
                }

                Text {
                    Layout.fillWidth: true
                    text: root.projectType === "batch"
                        ? qsTr("%1 - %2").arg(root.videoCount).arg(I18n.t("videos"))
                        : root.statusLabel
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    text: qsTr("%1%").arg(root.progress)
                    color: root.statusColor
                    font.pixelSize: Theme.caption
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                AppIcon {
                    Layout.preferredWidth: Theme.icon
                    Layout.preferredHeight: Theme.icon
                    glyph: "\uE76C"
                    iconColor: hoverHandler.hovered ? Theme.text : Theme.textSubtle
                    iconSize: Theme.iconSmall
                }
            }
        }
    }

    transform: Translate {
        y: hoverHandler.hovered ? -2 : 0
        Behavior on y {
            NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
        }
    }
    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on border.color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on scale {
        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
    }
}
