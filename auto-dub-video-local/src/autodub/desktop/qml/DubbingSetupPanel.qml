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
            enabled: !controller.isProcessing
            currentValue: controller.workflowMode
            options: [
                { "label": I18n.t("Full auto"), "value": "A" },
                { "label": I18n.t("Review then dub"), "value": "review" }
            ]
            onActivated: function(value) {
                controller.workflowMode = value
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
            enabled: !controller.isProcessing
            options: controller.targetLanguageOptions
            selectedCode: controller.targetLanguage
            onSelected: function(code) {
                controller.targetLanguage = code
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
            enabled: !controller.isProcessing
            textRole: "label"
            valueRole: "voice"
            model: controller.ttsVoiceOptions
            currentIndex: controller.ttsVoiceIndex
            onActivated: controller.ttsVoice = currentValue
        }
    }

    Rectangle {
        Layout.fillWidth: true
        Layout.preferredHeight: 1
        Layout.topMargin: Theme.space4
        Layout.bottomMargin: Theme.space4
        color: Theme.divider
    }

    AppCheckBox {
        Layout.fillWidth: true
        enabled: !controller.isProcessing
        text: I18n.t("Separate vocals for music or noisy audio")
        checked: controller.enableAudioSeparation
        onToggled: controller.enableAudioSeparation = checked
    }

    ColumnLayout {
        Layout.fillWidth: true
        spacing: Theme.space8

        RowLayout {
            Layout.fillWidth: true

            Text {
                Layout.fillWidth: true
                text: I18n.t("Original audio")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                font.weight: Font.Medium
                textFormat: Text.PlainText
            }

            Text {
                text: qsTr("%1%").arg(controller.originalVolume)
                color: Theme.text
                font.pixelSize: Theme.caption
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }
        }

        AppSlider {
            Layout.fillWidth: true
            enabled: !controller.isProcessing
            from: 0
            to: 100
            stepSize: 1
            value: controller.originalVolume
            Accessible.name: I18n.t("Original audio")
            onMoved: controller.originalVolume = Math.round(value)
        }
    }

    Item {
        Layout.fillHeight: true
        Layout.minimumHeight: Theme.space8
    }

    AppButton {
        Layout.fillWidth: true
        visible: controller.isSelectedBatchJob
        text: I18n.t("Save video settings")
        iconGlyph: "\uE74E"
        tone: "primary"
        enabled: !controller.isProcessing
        onClicked: controller.saveSelectedJobSettings()
    }

    AppButton {
        Layout.fillWidth: true
        visible: !controller.hasSelectedJob
        text: controller.isProcessing ? I18n.t("A job is already processing") : I18n.t("Create and process")
        iconGlyph: "\uE768"
        tone: "primary"
        enabled: !controller.isProcessing && controller.videoPath.length > 0
        onClicked: controller.startProjectJob()
    }
}
