import QtQuick
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    signal backToJobs()

    spacing: Theme.gap

    RowLayout {
        Layout.fillWidth: true
        spacing: 14

        AppButton {
            Layout.preferredWidth: 82
            text: qsTr("Back")
            tone: "ghost"
            onClicked: root.backToJobs()
        }

        PageHeader {
            Layout.fillWidth: true
            title: controller.selectedFileName || qsTr("Job detail")
            subtitle: qsTr("%1  /  HY-MT2  /  %2  /  Updated %3")
                .arg(controller.selectedTargetLanguageLabel)
                .arg(controller.selectedOutputFormat)
                .arg(controller.selectedUpdatedAt)

            StatusPill {
                status: controller.selectedStatus
                label: controller.selectedStatus
            }
        }
    }

    RowLayout {
        Layout.fillWidth: true
        Layout.fillHeight: true
        spacing: Theme.gap

        ColumnLayout {
            Layout.preferredWidth: 360
            Layout.minimumWidth: 340
            Layout.maximumWidth: 380
            Layout.fillWidth: false
            Layout.fillHeight: true
            spacing: Theme.gap

            Panel {
                Layout.fillWidth: true
                title: qsTr("Run status")
                subtitle: qsTr("Live pipeline progress")

                RowLayout {
                    Layout.fillWidth: true

                    Text {
                        Layout.fillWidth: true
                        text: controller.selectedStep
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
                }

                AppProgressBar {
                    Layout.fillWidth: true
                    value: controller.selectedProgress
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.outline
                }

                InfoRow {
                    Layout.fillWidth: true
                    label: qsTr("Status")
                    value: controller.selectedStatus
                }

                InfoRow {
                    Layout.fillWidth: true
                    label: qsTr("Target")
                    value: controller.selectedTargetLanguageLabel
                }

                InfoRow {
                    Layout.fillWidth: true
                    label: qsTr("Output")
                    value: controller.selectedOutputFormat
                }
            }

            Panel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Actions")
                subtitle: qsTr("Preview, export and manage this job")

                AppButton {
                    Layout.fillWidth: true
                    text: qsTr("Open input preview")
                    onClicked: controller.openInputPreview()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: qsTr("Open output video")
                    tone: "primary"
                    onClicked: controller.openOutputFile()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: qsTr("Open output folder")
                    onClicked: controller.openOutputFolder()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: qsTr("Open job folder")
                    onClicked: controller.openJobFolder()
                }

                Item {
                    Layout.fillHeight: true
                }

                AppButton {
                    Layout.fillWidth: true
                    text: qsTr("Delete job")
                    tone: "danger"
                    onClicked: controller.deleteSelectedJob()
                }
            }
        }

        Panel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: qsTr("Activity log")
            subtitle: qsTr("Processing output for this job")

            LogViewer {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: controller.logs
                emptyText: qsTr("No log entries for this job yet.")
            }
        }
    }
}
