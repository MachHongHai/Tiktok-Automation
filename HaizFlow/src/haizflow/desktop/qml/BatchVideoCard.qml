import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string fileName
    required property string status
    required property int progress
    required property string thumbnailSource
    required property string videoSize
    required property bool subtitleOverride

    signal activated()

    readonly property string statusLabel: status === "pending" ? I18n.t("Queued")
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
        : Theme.textMuted

    radius: Theme.radius
    color: hoverHandler.hovered ? Theme.surfaceMuted : Theme.surface
    border.width: activeFocus ? 2 : 1
    border.color: activeFocus ? Theme.focus : hoverHandler.hovered ? Theme.outlineStrong : Theme.outline
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: fileName
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
            Layout.preferredHeight: Math.round(root.width * 0.58)
            radius: Theme.radius
            color: Theme.video
            clip: true

            Image {
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: Math.round(root.width * 2)
                sourceSize.height: Math.round(root.width * 1.16)
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                visible: status === Image.Ready
            }

            AppIcon {
                anchors.centerIn: parent
                visible: root.thumbnailSource.length === 0
                width: 28
                height: 28
                glyph: "\uE714"
                iconColor: Theme.textSubtle
                iconSize: Theme.iconLarge
            }

            Row {
                anchors.top: parent.top
                anchors.right: parent.right
                anchors.margins: Theme.space8
                spacing: Theme.space4

                Rectangle {
                    width: sizeLabel.implicitWidth + Theme.space12
                    height: 26
                    radius: Theme.radiusSmall
                    color: Theme.scrim

                    Text {
                        id: sizeLabel
                        anchors.centerIn: parent
                        text: I18n.t(root.videoSize)
                        color: Theme.textOnDark
                        font.pixelSize: Theme.label
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }

                Rectangle {
                    visible: root.subtitleOverride
                    width: customLabel.implicitWidth + Theme.space12
                    height: 26
                    radius: Theme.radiusSmall
                    color: Theme.interactive

                    Text {
                        id: customLabel
                        anchors.centerIn: parent
                        text: I18n.t("Custom")
                        color: Theme.textOnAccent
                        font.pixelSize: Theme.label
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: Theme.space12
            Layout.rightMargin: Theme.space12
            Layout.topMargin: Theme.space8
            Layout.bottomMargin: Theme.space8
            spacing: Theme.space4

            Text {
                Layout.fillWidth: true
                text: root.fileName
                color: Theme.text
                font.pixelSize: Theme.body
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
                    text: root.statusLabel
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
