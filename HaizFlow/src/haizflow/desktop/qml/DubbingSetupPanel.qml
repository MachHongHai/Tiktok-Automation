import QtQuick
import QtQuick.Layouts
import "."

Panel {
    id: root

    title: I18n.t("Dubbing setup")
    subtitle: I18n.t("Language, voice and output behavior")

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            text: I18n.t("Workflow")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        SegmentedControl {
            Layout.fillWidth: true
            enabled: AppController.canEditSelectedVideo
            currentValue: AppController.workflowMode
            options: [
                { "label": I18n.t("Full auto"), "value": "A" },
                { "label": I18n.t("Review then dub"), "value": "review" }
            ]
            onActivated: function(value) {
                AppController.workflowMode = value
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            text: I18n.t("Translate to")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        SearchableLanguageCombo {
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            enabled: AppController.canEditSelectedVideo
            options: AppController.targetLanguageOptions
            selectedCode: AppController.targetLanguage
            onSelected: function(code) {
                AppController.targetLanguage = code
            }
        }
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            text: I18n.t("Voice")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        AppComboBox {
            Layout.fillWidth: true
            enabled: AppController.canEditSelectedVideo
            textRole: "label"
            valueRole: "voice"
            model: AppController.ttsVoiceOptions
            currentIndex: AppController.ttsVoiceIndex
            onActivated: AppController.ttsVoice = currentValue
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        Layout.topMargin: Theme.space4
        Layout.bottomMargin: Theme.space4
        color: Theme.divider
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        Text {
            text: I18n.t("Audio source")
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            font.weight: Font.Medium
            textFormat: Text.PlainText
        }

        SegmentedControl {
            Layout.fillWidth: true
            enabled: AppController.canEditSelectedVideo
            currentValue: AppController.enableAudioSeparation ? "separated" : "original"
            options: [
                { "label": I18n.t("Keep original audio"), "value": "original" },
                { "label": I18n.t("Separate vocals"), "value": "separated" }
            ]
            onActivated: function(value) {
                AppController.enableAudioSeparation = value === "separated"
            }
        }
    }

    Text {
        Layout.fillWidth: true
        visible: AppController.cpuOnly && AppController.enableAudioSeparation
        text: I18n.t("Audio separation is slower in CPU mode")
        color: Theme.warning
        font.pixelSize: Theme.caption
        wrapMode: Text.Wrap
        textFormat: Text.PlainText
    }

    ColumnLayout {
        Layout.fillWidth: true
        visible: !AppController.enableAudioSeparation
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true

            Text {
                Layout.fillWidth: true
                text: I18n.t("Original audio volume")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                textFormat: Text.PlainText
            }

            Text {
                text: qsTr("%1%").arg(AppController.originalVolume)
                color: Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
        }

        AppSlider {
            Layout.fillWidth: true
            enabled: AppController.canEditSelectedVideo
            from: 0
            to: 100
            stepSize: 1
            value: AppController.originalVolume
            Accessible.name: I18n.t("Original audio volume")
            onMoved: AppController.originalVolume = Math.round(value)
        }
    }

    Item {
        Layout.fillHeight: true
        Layout.minimumHeight: Theme.space8
    }

    AppButton {
        Layout.fillWidth: true
        visible: AppController.isSelectedBatchVideo
        text: I18n.t("Save video settings")
        iconGlyph: "\uE74E"
        tone: "primary"
        enabled: AppController.canEditSelectedVideo
        onClicked: AppController.saveSelectedVideoSettings()
    }

    AppButton {
        Layout.fillWidth: true
        visible: !AppController.hasSelectedVideo
        text: AppController.isProcessing ? I18n.t("Add to processing queue") : I18n.t("Create and process")
        iconGlyph: "\uE768"
        tone: "primary"
        enabled: AppController.canEditSelectedVideo && AppController.videoPath.length > 0
        onClicked: AppController.startProjectVideo()
    }
}
