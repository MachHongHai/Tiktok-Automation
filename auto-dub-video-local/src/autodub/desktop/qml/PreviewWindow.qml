import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import QtMultimedia
import "."

Window {
    id: root

    width: 1320
    height: 840
    minimumWidth: 900
    minimumHeight: 620
    title: controller.previewTitle
    color: Theme.window

    property real videoRatio: Math.max(0.1, controller.previewAspectRatio)
    property bool showPoster: false

    onClosing: player.stop()

    function openFromController() {
        player.stop()
        player.source = ""
        player.source = controller.previewSource
        showPoster = controller.previewPosterSource.length > 0
        subtitleBox.resetFromController()
        visible = true
        raise()
        requestActivate()
    }

    MediaPlayer {
        id: player
        audioOutput: AudioOutput {
            volume: 0.6
        }
        videoOutput: videoOutput
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: 18
        spacing: 14

        RowLayout {
            Layout.fillWidth: true
            spacing: 12

            Rectangle {
                Layout.preferredWidth: 38
                Layout.preferredHeight: 38
                radius: Theme.radius
                color: Theme.interactiveMuted
                border.width: 1
                border.color: Theme.interactive

                Text {
                    anchors.centerIn: parent
                    text: controller.previewInteractive ? "S" : "V"
                    color: Theme.interactive
                    font.pixelSize: Theme.caption
                    font.weight: Font.Bold
                    textFormat: Text.PlainText
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 1

                Text {
                    Layout.fillWidth: true
                    text: controller.previewTitle
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    Layout.fillWidth: true
                    text: controller.previewInteractive
                          ? qsTr("Drag the frame or resize from any edge")
                          : qsTr("Review the rendered output")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }
            }

            AppButton {
                Layout.preferredWidth: 110
                text: player.playbackState === MediaPlayer.PlayingState ? qsTr("Pause") : qsTr("Play")
                tone: "primary"
                onClicked: {
                    if (player.playbackState === MediaPlayer.PlayingState) {
                        player.pause()
                    } else {
                        root.showPoster = false
                        player.play()
                    }
                }
            }

            AppButton {
                Layout.preferredWidth: 92
                text: qsTr("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            id: videoFrame
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: "#000000"
            radius: Theme.radius
            border.width: 1
            border.color: Theme.outlineStrong
            clip: true

            Item {
                id: contentArea
                width: videoFrame.width / videoFrame.height > root.videoRatio ? videoFrame.height * root.videoRatio : videoFrame.width
                height: videoFrame.width / videoFrame.height > root.videoRatio ? videoFrame.height : videoFrame.width / root.videoRatio
                x: (videoFrame.width - width) / 2
                y: (videoFrame.height - height) / 2

                VideoOutput {
                    id: videoOutput
                    anchors.fill: parent
                    fillMode: VideoOutput.Stretch
                }

                Image {
                    id: posterFrame
                    anchors.fill: parent
                    source: controller.previewPosterSource
                    sourceSize.width: Math.round(contentArea.width)
                    sourceSize.height: Math.round(contentArea.height)
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: root.showPoster && status === Image.Ready
                }

                SubtitleEditBox {
                    id: subtitleBox
                    onEdited: function(xPercent, yPercent, widthPercent, heightPercent, fontSize) {
                        controller.updatePreviewEdits(xPercent, yPercent, widthPercent, heightPercent, fontSize)
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 54
            radius: Theme.radius
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 12

                Text {
                    Layout.preferredWidth: 46
                    text: formatTime(player.position)
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                AppSlider {
                    id: timeline
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(1, player.duration)
                    value: player.position
                    onMoved: {
                        root.showPoster = false
                        player.position = value
                    }
                }

                Text {
                    Layout.preferredWidth: 46
                    text: formatTime(player.duration)
                    color: Theme.textMuted
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }
        }
    }

    function formatTime(milliseconds) {
        var total = Math.max(0, Math.floor(milliseconds / 1000))
        var minutes = Math.floor(total / 60)
        var seconds = total % 60
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0")
    }
}
