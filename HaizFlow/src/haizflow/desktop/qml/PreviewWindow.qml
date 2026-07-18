import QtQuick
import QtQuick.Layouts
import QtMultimedia
import "."

Window {
    id: root
    objectName: "previewWindow"

    width: 1320
    height: 840
    minimumWidth: 900
    minimumHeight: 620
    title: I18n.t(AppController.previewTitle)
    color: Theme.window

    property real videoRatio: Math.max(0.1, AppController.previewAspectRatio)
    property bool showPoster: false
    property bool userPlaybackRequested: false
    property bool editHandled: false
    property bool editsSaved: false
    property bool returnToBatchSetup: false

    signal batchSetupReturnRequested()

    onClosing: {
        player.stop()
        if (AppController.previewInteractive && !editHandled)
            AppController.cancelPreviewEdits()
    }
    onVisibleChanged: {
        if (!visible) {
            player.stop()
            if (returnToBatchSetup) {
                returnToBatchSetup = false
                batchSetupReturnRequested()
            }
        }
    }

    function openFromController() {
        player.stop()
        player.source = ""
        player.source = AppController.previewSource
        showPoster = AppController.previewPosterSource.length > 0
        userPlaybackRequested = false
        editHandled = false
        editsSaved = false
        subtitleBox.resetFromController()
        visible = true
        raise()
        requestActivate()
    }

    function togglePlayback() {
        if (userPlaybackRequested) {
            userPlaybackRequested = false
            player.pause()
        } else {
            root.showPoster = false
            if (player.mediaStatus === MediaPlayer.EndOfMedia)
                player.position = 0
            userPlaybackRequested = true
            player.play()
        }
    }

    function formatTime(milliseconds) {
        var total = Math.max(0, Math.floor(milliseconds / 1000))
        var minutes = Math.floor(total / 60)
        var seconds = total % 60
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0")
    }

    Shortcut {
        sequence: "Space"
        onActivated: root.togglePlayback()
    }

    MediaPlayer {
        id: player
        audioOutput: AudioOutput {
            volume: 0.6
            muted: false
        }
        videoOutput: videoOutput

        onErrorOccurred: {
            root.userPlaybackRequested = false
        }

        onPlaybackStateChanged: {
            if (playbackState !== MediaPlayer.PlayingState) {
                root.userPlaybackRequested = false
            }
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            color: Theme.topBar

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space20
                anchors.rightMargin: Theme.space16
                spacing: Theme.space12

                AppIcon {
                    Layout.preferredWidth: 30
                    Layout.preferredHeight: 30
                    glyph: AppController.previewInteractive ? "\uE70F" : "\uE714"
                    iconColor: Theme.interactive
                    iconSize: Theme.iconLarge
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t(AppController.previewTitle)
                        color: Theme.text
                        font.pixelSize: Theme.h2
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    Text {
                        Layout.fillWidth: true
                        text: AppController.previewInteractive
                            ? I18n.t("Subtitle placement")
                            : I18n.t("Output preview")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }

                AppButton {
                    text: root.userPlaybackRequested ? I18n.t("Pause") : I18n.t("Play")
                    iconGlyph: root.userPlaybackRequested ? "\uE769" : "\uE768"
                    tone: "primary"
                    onClicked: root.togglePlayback()
                }

                AppButton {
                    visible: AppController.previewInteractive
                    text: I18n.t(AppController.previewSaveLabel)
                    iconGlyph: "\uE74E"
                    tone: "primary"
                    enabled: !root.editsSaved
                    onClicked: {
                        if (AppController.commitPreviewEdits()) {
                            root.editHandled = true
                            root.editsSaved = true
                        }
                    }
                }

                AppButton {
                    text: I18n.t("Close")
                    iconGlyph: "\uE711"
                    tone: "ghost"
                    onClicked: {
                        if (AppController.previewInteractive)
                            AppController.cancelPreviewEdits()
                        root.editHandled = true
                        root.close()
                    }
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: Theme.divider
            }
        }

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space16

            Rectangle {
                id: videoFrame
                anchors.fill: parent
                color: Theme.video
                radius: Theme.radius
                border.width: 1
                border.color: Theme.outlineStrong
                clip: true

                Item {
                    id: contentArea
                    width: videoFrame.width / videoFrame.height > root.videoRatio
                        ? videoFrame.height * root.videoRatio
                        : videoFrame.width
                    height: videoFrame.width / videoFrame.height > root.videoRatio
                        ? videoFrame.height
                        : videoFrame.width / root.videoRatio
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
                        source: AppController.previewPosterSource
                        sourceSize.width: Math.round(contentArea.width)
                        sourceSize.height: Math.round(contentArea.height)
                        fillMode: Image.PreserveAspectFit
                        visible: root.showPoster && status === Image.Ready
                        opacity: visible ? 1 : 0

                        Behavior on opacity {
                            NumberAnimation { duration: Theme.motionStandard }
                        }
                    }

                    SubtitleEditBox {
                        id: subtitleBox
                        onEdited: function(xPercent, yPercent, widthPercent, heightPercent, fontSize) {
                            root.editsSaved = false
                            AppController.updatePreviewEdits(xPercent, yPercent, widthPercent, heightPercent, fontSize)
                        }
                    }
                }

                IconButton {
                    anchors.centerIn: parent
                    visible: root.showPoster
                    controlSize: 58
                    glyph: "\uE768"
                    tone: "primary"
                    toolTipText: I18n.t("Play")
                    onClicked: root.togglePlayback()
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 64
            color: Theme.surface
            border.width: 0

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space20
                anchors.rightMargin: Theme.space20
                spacing: Theme.space12

                Text {
                    Layout.preferredWidth: 48
                    text: root.formatTime(player.position)
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }

                AppSlider {
                    id: timeline
                    Layout.fillWidth: true
                    from: 0
                    to: Math.max(1, player.duration)
                    value: player.position
                    Accessible.name: I18n.t("Video timeline")
                    onMoved: {
                        root.showPoster = false
                        player.position = value
                    }
                }

                Text {
                    Layout.preferredWidth: 48
                    text: root.formatTime(player.duration)
                    color: Theme.textMuted
                    horizontalAlignment: Text.AlignRight
                    font.pixelSize: Theme.caption
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 1
                color: Theme.divider
            }
        }
    }
}
