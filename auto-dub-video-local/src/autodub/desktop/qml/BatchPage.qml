import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    signal openJobDetail()

    spacing: Theme.gap

    PageHeader {
        Layout.fillWidth: true
        title: qsTr("Batch queue")
        subtitle: qsTr("Process a video collection with one shared dubbing setup.")

        AppButton {
            text: qsTr("Clear")
            enabled: controller.batchCount > 0 && !controller.isBatchRunning
            onClicked: controller.clearBatch()
        }

        AppButton {
            text: qsTr("Add videos")
            enabled: !controller.isBatchRunning
            onClicked: controller.browseBatchVideos()
        }

        AppButton {
            text: controller.isBatchRunning ? qsTr("Running queue") : qsTr("Start queue")
            tone: "primary"
            enabled: controller.batchPendingCount > 0 && !controller.isProcessing
            onClicked: controller.startBatch()
        }

        AppButton {
            text: qsTr("Stop")
            tone: "danger"
            enabled: controller.isBatchRunning
            onClicked: controller.stopBatch()
        }
    }

    Panel {
        Layout.fillWidth: true
        Layout.preferredHeight: 88
        headerVisible: false

        RowLayout {
            Layout.fillWidth: true
            spacing: 22

            InfoRow {
                Layout.preferredWidth: 150
                label: qsTr("Videos")
                value: String(controller.batchCount)
            }

            InfoRow {
                Layout.preferredWidth: 170
                label: qsTr("Completed")
                value: qsTr("%1 / %2").arg(controller.batchCompletedCount).arg(controller.batchCount)
            }

            InfoRow {
                Layout.preferredWidth: 250
                label: qsTr("Target")
                value: controller.batchTargetLanguageLabel
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 7

                RowLayout {
                    Layout.fillWidth: true

                    Text {
                        Layout.fillWidth: true
                        text: controller.isBatchRunning ? qsTr("Queue processing") : qsTr("Overall progress")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    Text {
                        text: qsTr("%1%").arg(controller.batchProgress)
                        color: Theme.text
                        font.pixelSize: Theme.caption
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                    }
                }

                AppProgressBar {
                    Layout.fillWidth: true
                    value: controller.batchProgress
                }
            }
        }
    }

    Panel {
        Layout.fillWidth: true
        Layout.fillHeight: true
        title: qsTr("Video jobs")
        subtitle: qsTr("Newest additions appear at the bottom of this queue")

        Item {
            Layout.fillWidth: true
            Layout.fillHeight: true

            ListView {
                id: queueList

                anchors.fill: parent
                clip: true
                spacing: 8
                model: controller.batchJobModel
                reuseItems: true

                delegate: BatchJobRow {
                    onActivated: {
                        controller.selectBatchJob(index)
                        root.openJobDetail()
                    }
                }

                ScrollBar.vertical: ScrollBar {}
            }

            Column {
                anchors.centerIn: parent
                width: Math.min(420, parent.width - 40)
                spacing: 8
                visible: controller.batchCount === 0

                Text {
                    width: parent.width
                    text: qsTr("Add videos to build a batch")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.Medium
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }

                Text {
                    width: parent.width
                    text: qsTr("Drop MP4, MOV or MKV files here")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    horizontalAlignment: Text.AlignHCenter
                    textFormat: Text.PlainText
                }
            }

            DropArea {
                anchors.fill: parent
                keys: ["text/uri-list"]

                onEntered: function(drag) {
                    if (drag.hasUrls && !controller.isBatchRunning) {
                        drag.accept()
                    }
                }
                onDropped: function(drop) {
                    if (!drop.urls || drop.urls.length === 0 || controller.isBatchRunning) {
                        return
                    }
                    var paths = []
                    for (var i = 0; i < drop.urls.length; i++) {
                        paths.push(String(drop.urls[i]))
                    }
                    controller.importBatchVideos(paths)
                }
            }
        }
    }
}
