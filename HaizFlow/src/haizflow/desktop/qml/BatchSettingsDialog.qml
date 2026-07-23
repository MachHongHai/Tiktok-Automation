pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    objectName: "batchSettingsDialog"

    signal requestEditAllSubtitles()
    signal requestEditSubtitleSize(string sizeKey)
    property bool changesApplied: false
    property bool preserveDraftOnNextOpen: false
    property string draftWorkflowMode: "A"
    property string draftTargetLanguage: "vi"
    property string draftTtsVoice: ""
    property bool draftEnableAudioSeparation: false
    property int draftOriginalVolume: 60
    readonly property var draftVoiceOptions: AppController.voiceOptionsForLanguage(draftTargetLanguage)
    readonly property int draftTtsVoiceIndex: {
        for (let index = 0; index < draftVoiceOptions.length; ++index) {
            if (draftVoiceOptions[index].voice === draftTtsVoice)
                return index
        }
        return 0
    }

    function normalizedDraftVoice(languageCode, preferredVoice) {
        const options = AppController.voiceOptionsForLanguage(languageCode)
        for (let index = 0; index < options.length; ++index) {
            if (options[index].voice === preferredVoice)
                return preferredVoice
        }
        return options.length > 0 ? options[0].voice : ""
    }

    function loadDraft() {
        const settings = AppController.batchSettings()
        draftWorkflowMode = settings.workflowMode || "A"
        draftTargetLanguage = settings.targetLanguage || "vi"
        draftTtsVoice = normalizedDraftVoice(draftTargetLanguage, settings.ttsVoice || "")
        draftEnableAudioSeparation = Boolean(settings.enableAudioSeparation)
        draftOriginalVolume = Number(settings.originalVolume !== undefined ? settings.originalVolume : 60)
    }

    function preserveDraftForSubtitleEditor() {
        preserveDraftOnNextOpen = true
    }

    modal: true
    focus: true
    width: Math.min(720, parent ? parent.width - 48 : 720)
    height: Math.min(700, parent ? parent.height - 48 : 700)
    padding: 0
    title: I18n.t("Batch settings")
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

    onOpened: {
        changesApplied = false
        if (preserveDraftOnNextOpen)
            preserveDraftOnNextOpen = false
        else
            loadDraft()
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation { property: "scale"; from: 0.98; to: 1; duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }

    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
            NumberAnimation { property: "scale"; from: 1; to: 0.99; duration: Theme.motionFast }
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Batch settings")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Configure dubbing and subtitle presets for this batch")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ScrollView {
            id: detailsScroll

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: availableWidth

            ColumnLayout {
                width: detailsScroll.availableWidth
                spacing: Theme.space20

                GridLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space24
                    Layout.rightMargin: Theme.space24
                    Layout.topMargin: Theme.space20
                    columns: 2
                    columnSpacing: Theme.space24
                    rowSpacing: Theme.space16

                    Text {
                        Layout.columnSpan: 2
                        text: I18n.t("Dubbing and audio")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        text: I18n.t("Workflow")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    SegmentedControl {
                        Layout.fillWidth: true
                        currentValue: root.draftWorkflowMode
                        options: [
                            { "label": I18n.t("Full auto"), "value": "A" },
                            { "label": I18n.t("Review then dub"), "value": "review" }
                        ]
                        onActivated: function(value) {
                            root.changesApplied = false
                            root.draftWorkflowMode = value
                        }
                    }

                    Text {
                        text: I18n.t("Translate to")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    SearchableLanguageCombo {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        options: AppController.targetLanguageOptions
                        selectedCode: root.draftTargetLanguage
                        onSelected: function(code) {
                            root.changesApplied = false
                            root.draftTargetLanguage = code
                            root.draftTtsVoice = root.normalizedDraftVoice(code, root.draftTtsVoice)
                        }
                    }

                    Text {
                        text: I18n.t("Voice")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    AppComboBox {
                        Layout.fillWidth: true
                        textRole: "label"
                        valueRole: "voice"
                        model: root.draftVoiceOptions
                        currentIndex: root.draftTtsVoiceIndex
                        onActivated: {
                            root.changesApplied = false
                            root.draftTtsVoice = currentValue
                        }
                    }

                    Rectangle {
                        Layout.columnSpan: 2
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        color: Theme.divider
                    }

                    Text {
                        text: I18n.t("Audio source")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    SegmentedControl {
                        Layout.fillWidth: true
                        currentValue: root.draftEnableAudioSeparation ? "separated" : "original"
                        options: [
                            { "label": I18n.t("Keep original audio"), "value": "original" },
                            { "label": I18n.t("Separate vocals"), "value": "separated" }
                        ]
                        onActivated: function(value) {
                            root.changesApplied = false
                            root.draftEnableAudioSeparation = value === "separated"
                        }
                    }

                    Text {
                        visible: !root.draftEnableAudioSeparation
                        text: I18n.t("Original audio volume")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        visible: !root.draftEnableAudioSeparation
                        spacing: Theme.space12

                        AppSlider {
                            Layout.fillWidth: true
                            from: 0
                            to: 100
                            stepSize: 1
                            value: root.draftOriginalVolume
                            onMoved: {
                                root.changesApplied = false
                                root.draftOriginalVolume = Math.round(value)
                            }
                        }

                        Text {
                            Layout.preferredWidth: 44
                            text: qsTr("%1%").arg(root.draftOriginalVolume)
                            color: Theme.text
                            horizontalAlignment: Text.AlignRight
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.leftMargin: Theme.space24
                    Layout.rightMargin: Theme.space24
                    Layout.bottomMargin: Theme.space20
                    spacing: Theme.space12

                    RowLayout {
                        Layout.fillWidth: true

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 2

                            Text {
                                Layout.fillWidth: true
                                text: I18n.t("Subtitle presets")
                                color: Theme.text
                                font.pixelSize: Theme.body
                                font.weight: Font.DemiBold
                                textFormat: Text.PlainText
                            }

                            Text {
                                Layout.fillWidth: true
                                text: I18n.t("One subtitle frame is shared by each video size")
                                color: Theme.textMuted
                                font.pixelSize: Theme.caption
                                textFormat: Text.PlainText
                            }
                        }

                        AppButton {
                            text: I18n.t("Edit all subtitles")
                            iconGlyph: "\uE70F"
                            enabled: AppController.batchCount > 0 && !AppController.isBatchRunning
                            onClicked: root.requestEditAllSubtitles()
                        }
                    }

                    Repeater {
                        model: AppController.batchVideoSizeGroups

                        delegate: Rectangle {
                            id: sizePreset

                            required property var modelData

                            Layout.fillWidth: true
                            Layout.preferredHeight: 58
                            radius: Theme.radiusSmall
                            color: Theme.surfaceElevated
                            border.width: 1
                            border.color: Theme.outline

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: Theme.space12
                                anchors.rightMargin: Theme.space8
                                spacing: Theme.space12

                                AppIcon {
                                    Layout.preferredWidth: Theme.icon
                                    Layout.preferredHeight: Theme.icon
                                    glyph: "\uE714"
                                    iconColor: Theme.textMuted
                                    iconSize: Theme.iconSmall
                                }

                                Text {
                                    Layout.preferredWidth: 110
                                    text: I18n.t(sizePreset.modelData.label)
                                    color: Theme.text
                                    font.pixelSize: Theme.caption
                                    font.weight: Font.DemiBold
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                }

                                Text {
                                    Layout.fillWidth: true
                                    text: qsTr("%1 %2").arg(sizePreset.modelData.count).arg(I18n.t("videos"))
                                        + (sizePreset.modelData.customizedCount > 0
                                            ? qsTr(" | %1 %2").arg(sizePreset.modelData.customizedCount).arg(I18n.t("custom"))
                                            : "")
                                    color: Theme.textMuted
                                    font.pixelSize: Theme.caption
                                    textFormat: Text.PlainText
                                    elide: Text.ElideRight
                                }

                                AppButton {
                                    text: I18n.t("Edit")
                                    iconGlyph: "\uE70F"
                                    compact: true
                                    enabled: !AppController.isBatchRunning
                                    onClicked: root.requestEditSubtitleSize(sizePreset.modelData.sizeKey)
                                }
                            }
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space24
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: qsTr("%1 %2").arg(AppController.batchCount).arg(I18n.t("videos"))
                color: Theme.textMuted
                font.pixelSize: Theme.caption
            }

            AppButton {
                text: I18n.t("Cancel")
                tone: "ghost"
                onClicked: root.close()
            }

            AppButton {
                text: I18n.t("Apply to all videos")
                iconGlyph: "\uE73E"
                tone: "primary"
                enabled: AppController.batchCount > 0 && !root.changesApplied
                onClicked: {
                    if (AppController.applyBatchSettingsDraft(
                            root.draftWorkflowMode,
                            root.draftTargetLanguage,
                            root.draftTtsVoice,
                            root.draftEnableAudioSeparation,
                            root.draftOriginalVolume
                        ))
                        root.changesApplied = true
                }
            }
        }
    }
}
