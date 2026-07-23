pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestBack
    signal openVideoDetail
    signal requestBatchSettings
    signal requestUrlImport
    signal requestChannelImport

    property bool dropActive: false
    readonly property bool hasChannelImport: AppController.hasChannelImportSession
    readonly property bool compactHeight: height < 740

    opacity: visible ? 1 : 0
    transform: Translate {
        y: root.visible ? 0 : 8
        Behavior on y {
            NumberAnimation {
                duration: Theme.motionStandard
                easing.type: Easing.OutCubic
            }
        }
    }
    Behavior on opacity {
        NumberAnimation {
            duration: Theme.motionStandard
        }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.topMargin: root.compactHeight ? Theme.space12 : Theme.space20
        spacing: root.compactHeight ? Theme.space12 : Theme.space20

        PageHeader {
            Layout.fillWidth: true
            Layout.minimumHeight: root.compactHeight ? 52 : 58
            Layout.preferredHeight: root.compactHeight ? 52 : 58
            title: AppController.projectName || I18n.t("Batch project")
            subtitle: qsTr("%1 %2").arg(AppController.batchCount).arg(I18n.t("videos"))

            AppButton {
                text: I18n.t("Back")
                iconGlyph: "\uE72B"
                tone: "secondary"
                onClicked: root.requestBack()
            }

            AppButton {
                text: I18n.t("Batch setup")
                iconGlyph: "\uE713"
                toolTipText: I18n.t("Configure this batch")
                enabled: AppController.batchCount > 0
                onClicked: root.requestBatchSettings()
            }

            AppButton {
                text: I18n.t("Open project folder")
                iconGlyph: "\uE8B7"
                enabled: AppController.hasOpenProject
                onClicked: AppController.openProjectFolder()
            }

            AppButton {
                text: I18n.t("Delete project")
                iconGlyph: "\uE74D"
                tone: "danger"
                enabled: AppController.hasOpenProject
                onClicked: AppController.deleteCurrentBatch()
            }

            AppButton {
                visible: !AppController.isBatchRunning
                text: I18n.t("Start queue")
                iconGlyph: "\uE768"
                tone: "primary"
                enabled: AppController.batchPendingCount > 0
                onClicked: AppController.startBatch()
            }

            AppButton {
                visible: AppController.isBatchRunning
                text: I18n.t("Stop queue")
                iconGlyph: "\uE71A"
                tone: "danger"
                onClicked: AppController.stopBatch()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: root.hasChannelImport ? (root.compactHeight ? 60 : 68) : 88
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space20
                anchors.rightMargin: Theme.space20
                spacing: Theme.space24

                InfoRow {
                    Layout.preferredWidth: 120
                    label: I18n.t("Videos")
                    value: String(AppController.batchCount)
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 38
                    color: Theme.divider
                }

                InfoRow {
                    Layout.preferredWidth: 150
                    label: I18n.t("Completed")
                    value: qsTr("%1 / %2").arg(AppController.batchCompletedCount).arg(AppController.batchCount)
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 38
                    color: Theme.divider
                }

                InfoRow {
                    Layout.preferredWidth: 260
                    label: I18n.t("Target")
                    value: I18n.t(AppController.batchTargetLanguageLabel)
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8

                    RowLayout {
                        Layout.fillWidth: true

                        Text {
                            Layout.fillWidth: true
                            text: AppController.isBatchRunning ? I18n.t("Queue processing") : I18n.t("Overall progress")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }

                        Text {
                            text: qsTr("%1%").arg(AppController.batchProgress)
                            color: AppController.batchProgress >= 100 ? Theme.success : Theme.text
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }
                    }

                    AppProgressBar {
                        Layout.fillWidth: true
                        value: AppController.batchProgress
                    }
                }
            }
        }

        Rectangle {
            id: importStrip

            Layout.fillWidth: true
            Layout.preferredHeight: root.hasChannelImport ? (root.compactHeight ? 60 : 68) : 88
            radius: Theme.radius
            color: root.dropActive ? Theme.interactiveMuted : Theme.surfaceElevated
            border.width: 1
            border.color: root.dropActive ? Theme.focus : Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: Theme.space20
                anchors.rightMargin: Theme.space12
                spacing: Theme.space12

                AppIcon {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    glyph: "\uE898"
                    iconColor: root.dropActive ? Theme.interactive : Theme.textMuted
                    iconSize: Theme.iconLarge
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: 2

                    Text {
                        Layout.fillWidth: true
                        text: root.dropActive ? I18n.t("Release to add videos") : I18n.t("Drop videos or a folder into the queue")
                        color: Theme.text
                        font.pixelSize: Theme.body
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: AppController.mediaImportBusy
                            ? qsTr("Adding %1 / %2 videos…").arg(AppController.mediaImportCompleted).arg(AppController.mediaImportTotal)
                            : I18n.t("Only MP4, MOV and MKV files are added")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }
                }

                AppButton {
                    text: I18n.t("Add videos")
                    iconGlyph: "\uE710"
                    onClicked: AppController.browseBatchVideos()
                }

                AppButton {
                    text: I18n.t("Add folder")
                    iconGlyph: "\uE8B7"
                    tone: "secondary"
                    onClicked: AppController.browseBatchFolder()
                }

                AppButton {
                    text: I18n.t("Video link")
                    iconGlyph: "\uE71B"
                    tone: "secondary"
                    onClicked: root.requestUrlImport()
                }

                AppButton {
                    text: root.hasChannelImport ? I18n.t("View progress") : I18n.t("Import channel")
                    iconGlyph: "\uE896"
                    tone: "primary"
                    onClicked: root.requestChannelImport()
                }
            }

            DropArea {
                anchors.fill: parent
                keys: ["text/uri-list"]
                onEntered: function (drag) {
                    if (drag.hasUrls) {
                        root.dropActive = true
                        drag.accept()
                    }
                }
                onExited: root.dropActive = false
                onDropped: function (drop) {
                    root.dropActive = false
                    if (!drop.urls || drop.urls.length === 0)
                        return
                    var paths = []
                    for (var i = 0; i < drop.urls.length; i++)
                        paths.push(String(drop.urls[i]))
                    AppController.importBatchVideos(paths)
                }
            }

            Behavior on color {
                ColorAnimation {
                    duration: Theme.motionFast
                }
            }
            Behavior on border.color {
                ColorAnimation {
                    duration: Theme.motionFast
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: visible ? (root.compactHeight ? 60 : 72) : 0
            visible: root.hasChannelImport
            radius: Theme.radius
            color: AppController.channelImportBusy ? Theme.interactiveMuted : Theme.surfaceElevated
            border.width: 1
            border.color: AppController.channelImportBusy ? Theme.focus : Theme.outline

            RowLayout {
                anchors.fill: parent
                anchors.topMargin: Theme.space8
                anchors.bottomMargin: Theme.space8
                anchors.leftMargin: Theme.space16
                anchors.rightMargin: Theme.space16
                spacing: Theme.space4

                AppIcon {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    glyph: "\uE896"
                    iconColor: AppController.channelImportBusy ? Theme.interactive : Theme.textMuted
                    iconSize: Theme.iconLarge
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: Theme.space8

                        Text {
                            Layout.fillWidth: true
                            text: AppController.channelImportName.length > 0 ? AppController.channelImportName : I18n.t("Import channel")
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }

                        Text {
                            text: qsTr("%1 / %2").arg(AppController.channelImportImportedCount).arg(AppController.channelImportCandidateCount)
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.channelImportStatus(AppController.channelImportStatus)
                        color: AppController.channelImportFailedCount > 0 ? Theme.warning : Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    AppProgressBar {
                        Layout.fillWidth: true
                        visible: AppController.channelImportBusy
                        value: AppController.channelImportProgress
                    }
                }

                AppButton {
                    text: I18n.t("View progress")
                    iconGlyph: "\uE76C"
                    tone: "secondary"
                    onClicked: root.requestChannelImport()
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: Theme.space12

            RowLayout {
                Layout.fillWidth: true

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Videos")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    visible: AppController.batchCount > 0
                    text: qsTr("%1 %2").arg(AppController.batchCount).arg(I18n.t("items"))
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            Rectangle {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: queueList.cellHeight + 20
                radius: Theme.radius
                color: Theme.surface
                border.width: 1
                border.color: Theme.outline

                GridView {
                    id: queueList

                    anchors.fill: parent
                    anchors.margins: AppController.batchCount > 0 ? 10 : 0
                    clip: true
                    model: AppController.batchVideoModel
                    reuseItems: true
                    cellWidth: Math.max(210, Math.floor((width - 16) / Math.max(2, Math.floor((width - 16) / 250))))
                    cellHeight: Math.round(cellWidth * 0.68 + 78)

                    delegate: BatchVideoCard {
                        width: queueList.cellWidth - Theme.space8
                        height: queueList.cellHeight - Theme.space8
                        onActivated: {
                            AppController.selectBatchVideo(index)
                            root.openVideoDetail()
                        }
                    }

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }
                }

                Column {
                    anchors.centerIn: parent
                    width: Math.min(420, parent.width - 40)
                    spacing: Theme.space8
                    visible: AppController.batchCount === 0

                    AppIcon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        width: 34
                        height: 34
                        glyph: "\uE8FD"
                        iconColor: Theme.textSubtle
                        iconSize: 28
                    }

                    Text {
                        width: parent.width
                        text: I18n.t("Your queue is empty")
                        color: Theme.text
                        font.pixelSize: Theme.h3
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                    }

                    Text {
                        width: parent.width
                        text: I18n.t("Add videos above to begin a batch")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                    }
                }
            }
        }
    }
}
