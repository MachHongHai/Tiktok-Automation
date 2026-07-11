import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    spacing: Theme.gap

    PageHeader {
        Layout.fillWidth: true
        title: controller.projectName || I18n.t("Create a new dub")
        subtitle: controller.projectDirectory || I18n.t("Turn one source video into a translated, voiced and captioned export.")
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Theme.gap

        Panel {
            Layout.preferredWidth: 400
            Layout.minimumWidth: 330
            Layout.maximumWidth: 430
            Layout.preferredHeight: 540
            Layout.alignment: Qt.AlignTop
            title: I18n.t("Source media")
            subtitle: I18n.t("Input video and subtitle placement")

            Rectangle {
                id: videoFrame

                property bool dropActive: sourceDropArea.containsDrag

                Layout.fillWidth: true
                Layout.preferredHeight: 260
                radius: Theme.radius
                color: dropActive ? "#0d1a1b" : "#090a0c"
                border.width: 1
                border.color: dropActive || controller.videoPath.length > 0 ? Theme.interactive : Theme.outline
                clip: true

                Image {
                    anchors.fill: parent
                    anchors.margins: 1
                    source: controller.videoThumbnailSource
                    sourceSize.width: 960
                    sourceSize.height: 540
                    fillMode: Image.PreserveAspectFit
                    asynchronous: true
                    visible: status === Image.Ready
                }

                Column {
                    anchors.centerIn: parent
                    width: Math.min(340, parent.width - 40)
                    spacing: 8
                    visible: controller.videoThumbnailSource.length === 0

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 44
                        height: 44
                        radius: 22
                        color: Theme.surfaceElevated
                        border.width: 1
                        border.color: Theme.outlineStrong

                        Text {
                            anchors.centerIn: parent
                            text: "+"
                            color: Theme.interactive
                            font.pixelSize: Theme.h2
                            textFormat: Text.PlainText
                        }
                    }

                    Text {
                        width: parent.width
                        text: videoFrame.dropActive ? I18n.t("Drop video to import") : I18n.t("Select a source video")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.Medium
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                    }

                    Text {
                        width: parent.width
                        text: videoFrame.dropActive ? I18n.t("Release to add the source file") : qsTr("MP4, MOV or MKV")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                    }
                }

                DropArea {
                    id: sourceDropArea
                    anchors.fill: parent
                    keys: ["text/uri-list"]

                    onEntered: function(drag) {
                        if (drag.hasUrls) {
                            drag.accept()
                        }
                }
                onDropped: function(drop) {
                    if (drop.urls && drop.urls.length > 0) {
                        controller.importVideo(String(drop.urls[0]))
                    }
                }
                }

                HoverHandler {
                    cursorShape: controller.videoPath.length === 0 ? Qt.PointingHandCursor : Qt.ArrowCursor
                }

                TapHandler {
                    enabled: controller.videoPath.length === 0
                    onTapped: controller.browseVideo()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 3

                    Text {
                        Layout.fillWidth: true
                        text: controller.videoPath.length > 0 ? I18n.t("Source imported") : I18n.t("No source selected")
                        color: controller.videoPath.length > 0 ? Theme.success : Theme.textMuted
                        font.pixelSize: Theme.caption
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: controller.videoPath || I18n.t("Choose a file to begin")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                        elide: Text.ElideMiddle
                    }
                }

                AppButton {
                    Layout.preferredWidth: 152
                    text: controller.videoPath.length > 0 ? I18n.t("Replace") : I18n.t("Browse")
                    onClicked: controller.browseVideo()
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Edit subtitle frame")
                    enabled: controller.videoPath.length > 0
                    onClicked: controller.openInputPreview()
                }

                Rectangle {
                    Layout.preferredWidth: 172
                    Layout.preferredHeight: 42
                    radius: Theme.radiusSmall
                    color: Theme.surfaceElevated
                    border.width: 1
                    border.color: Theme.outline

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 12
                        anchors.rightMargin: 12
                        spacing: 8

                        Rectangle {
                            Layout.preferredWidth: 8
                            Layout.preferredHeight: 8
                            radius: 4
                            color: Theme.blue
                        }

                        Text {
                            Layout.fillWidth: true
                            text: I18n.t("Full Auto workflow")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }
                }
            }
        }

        Panel {
            Layout.preferredWidth: 350
            Layout.minimumWidth: 300
            Layout.maximumWidth: 370
            Layout.preferredHeight: 540
            Layout.alignment: Qt.AlignTop
            title: I18n.t("Dubbing setup")
            subtitle: I18n.t("Language, voice and output behavior")

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                columnSpacing: 14
                rowSpacing: 12

                Text {
                    text: I18n.t("Source")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                AppComboBox {
                    Layout.fillWidth: true
                    model: ["auto", "en", "zh", "vi"]
                    currentIndex: model.indexOf(controller.sourceLanguage)
                    onActivated: controller.sourceLanguage = currentText
                }

                Text {
                    text: I18n.t("Translate to")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                SearchableLanguageCombo {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 42
                    options: controller.targetLanguageOptions
                    selectedCode: controller.targetLanguage
                    onSelected: function(code) {
                        controller.targetLanguage = code
                    }
                }

                Text {
                    text: I18n.t("Voice")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                AppComboBox {
                    Layout.fillWidth: true
                    textRole: "label"
                    valueRole: "voice"
                    model: controller.ttsVoiceOptions
                    currentIndex: controller.ttsVoiceIndex
                    onActivated: controller.ttsVoice = currentValue
                }

                Text {
                    text: I18n.t("Layout")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }

                AppComboBox {
                    Layout.fillWidth: true
                    textRole: "label"
                    valueRole: "value"
                    model: [
                        { "label": qsTr("Keep original ratio"), "value": "keep_ratio" },
                        { "label": qsTr("TikTok 9:16 crop"), "value": "tiktok_9_16_crop" },
                        { "label": qsTr("9:16 blur background"), "value": "blur_background_9_16" }
                    ]
                    currentIndex: {
                        for (var i = 0; i < model.length; i++) {
                            if (model[i].value === controller.outputFormat) {
                                return i
                            }
                        }
                        return 0
                    }
                    onActivated: controller.outputFormat = currentValue
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 1
                color: Theme.outline
            }

            AppCheckBox {
                Layout.fillWidth: true
                text: I18n.t("Separate vocals for music or noisy audio")
                checked: controller.enableAudioSeparation
                onToggled: controller.enableAudioSeparation = checked
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 7

                RowLayout {
                    Layout.fillWidth: true

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Original audio")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    Text {
                        text: qsTr("%1%").arg(controller.originalVolume)
                        color: Theme.text
                        font.pixelSize: Theme.caption
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                    }
                }

                AppSlider {
                    Layout.fillWidth: true
                    from: 0
                    to: 100
                    stepSize: 1
                    value: controller.originalVolume
                    onMoved: controller.originalVolume = Math.round(value)
                }
            }

            Item {
                Layout.fillHeight: true
            }

            AppButton {
                Layout.fillWidth: true
                text: controller.isProcessing ? qsTr("A job is already processing") : I18n.t("Create and process")
                tone: "primary"
                enabled: !controller.isProcessing && controller.videoPath.length > 0
                onClicked: controller.startProjectJob()
            }
        }

        Panel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.minimumWidth: 220
            title: I18n.t("Activity log")
            subtitle: controller.selectedTitle || I18n.t("Live processing output")

            LogViewer {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: controller.logs
                emptyText: qsTr("Logs will appear here while a job is processing.")
            }
        }
    }

    Panel {
        Layout.fillWidth: true
        Layout.preferredHeight: 138
        headerVisible: false

        RowLayout {
            Layout.fillWidth: true
            spacing: 18

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 6

                RowLayout {
                    Layout.fillWidth: true

                    Text {
                        Layout.fillWidth: true
                        text: controller.isProcessing
                              ? controller.processingText
                              : controller.selectedProgress >= 100
                              ? I18n.t("Last export ready")
                                : I18n.t("No active job")
                        color: Theme.text
                        font.pixelSize: Theme.h2
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    Text {
                        text: qsTr("%1%").arg(controller.selectedProgress)
                        color: Theme.interactive
                        font.pixelSize: Theme.h2
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                    }

                    Text {
                        visible: controller.selectedElapsed.length > 0
                        text: qsTr("Elapsed %1").arg(controller.selectedElapsed)
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    Text {
                        visible: controller.selectedEta.length > 0
                        text: qsTr("ETA %1").arg(controller.selectedEta)
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }

                Text {
                    Layout.fillWidth: true
                    text: controller.selectedStep || I18n.t("Processing status will appear here")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                AppProgressBar {
                    Layout.fillWidth: true
                    value: controller.selectedProgress
                }
            }

            AppButton {
                Layout.preferredWidth: 108
                text: I18n.t("Stop")
                tone: "danger"
                enabled: controller.isProcessing
                onClicked: controller.stopJob()
            }

            AppButton {
                Layout.preferredWidth: 164
                text: I18n.t("Open output")
                enabled: controller.selectedOutputPath.length > 0
                onClicked: controller.openOutputFile()
            }
        }
    }
}
