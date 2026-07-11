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
            Layout.preferredWidth: 124
            text: I18n.t("Back")
            tone: "ghost"
            onClicked: root.backToJobs()
        }

        PageHeader {
            Layout.fillWidth: true
            title: controller.selectedFileName || I18n.t("Job detail")
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
                title: I18n.t("Run status")
                subtitle: I18n.t("Live pipeline progress")

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
                    label: I18n.t("Status")
                    value: controller.selectedStatus
                }

                InfoRow {
                    Layout.fillWidth: true
                    label: I18n.t("Target")
                    value: controller.selectedTargetLanguageLabel
                }

                InfoRow {
                    Layout.fillWidth: true
                    label: I18n.t("Output")
                    value: controller.selectedOutputFormat
                }

                InfoRow {
                    Layout.fillWidth: true
                    visible: controller.selectedElapsed.length > 0
                    label: I18n.t("Elapsed")
                    value: controller.selectedElapsed
                }

                InfoRow {
                    Layout.fillWidth: true
                    visible: controller.selectedEta.length > 0
                    label: I18n.t("Estimated remaining")
                    value: controller.selectedEta
                }
            }

            Panel {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: I18n.t("Actions")
                subtitle: qsTr("Preview, export and manage this job")

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Open input video")
                    onClicked: controller.openInputFile()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Open output video")
                    tone: "primary"
                    onClicked: controller.openOutputFile()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Open output folder")
                    onClicked: controller.openOutputFolder()
                }

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Open job folder")
                    onClicked: controller.openJobFolder()
                }

                Item {
                    Layout.fillHeight: true
                }

                AppButton {
                    Layout.fillWidth: true
                    text: I18n.t("Delete job")
                    tone: "danger"
                    onClicked: controller.deleteSelectedJob()
                }
            }
        }

        Panel {
            Layout.fillWidth: true
            Layout.fillHeight: true
            title: I18n.t("Activity log")
            subtitle: I18n.t("Processing output for this job")

            LogViewer {
                Layout.fillWidth: true
                Layout.fillHeight: true
                text: controller.logs
                emptyText: qsTr("No log entries for this job yet.")
            }
        }
    }
}
