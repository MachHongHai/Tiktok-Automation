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
        title: I18n.t("Job library")
        subtitle: I18n.t("Review every run, inspect progress and reopen finished exports.")

        AppButton {
            text: I18n.t("Refresh")
            onClicked: controller.refreshJobs()
        }
    }

    Panel {
        Layout.fillWidth: true
        Layout.fillHeight: true
        title: I18n.t("Recent jobs")
        subtitle: I18n.t("Newest activity appears first")

        ListView {
            id: list

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            spacing: 8
            model: controller.jobModel
            reuseItems: true

            delegate: Rectangle {
                id: jobDelegate

                required property int index
                required property string fileName
                required property string mode
                required property string status
                required property string step
                required property string updatedAt
                required property int progress

                width: ListView.view.width
                height: 82
                radius: Theme.radiusSmall
                color: ListView.isCurrentItem ? Theme.interactiveMuted : hoverHandler.hovered ? Theme.surfaceMuted : Theme.surfaceElevated
                border.width: 1
                border.color: ListView.isCurrentItem ? Theme.interactive : Theme.outline

                HoverHandler {
                    id: hoverHandler
                    cursorShape: Qt.PointingHandCursor
                }

                TapHandler {
                    onTapped: {
                        list.currentIndex = index
                        controller.selectJob(index)
                        root.openJobDetail()
                    }
                }

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 13
                    spacing: 15

                    Rectangle {
                        Layout.preferredWidth: 42
                        Layout.preferredHeight: 42
                        radius: 7
                        color: status === "done" ? Theme.successMuted
                            : status === "failed" ? Theme.dangerMuted
                            : status === "processing" ? Theme.warningMuted
                            : Theme.surfaceStrong

                        Text {
                            anchors.centerIn: parent
                            text: status === "done" ? "OK" : status === "failed" ? "!" : status === "processing" ? ">" : "J"
                            color: status === "done" ? Theme.success
                                : status === "failed" ? Theme.danger
                                : status === "processing" ? Theme.warning
                                : Theme.textMuted
                            font.pixelSize: Theme.caption
                            font.weight: Font.Bold
                            textFormat: Text.PlainText
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 5

                        Text {
                            Layout.fillWidth: true
                            text: fileName
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.Medium
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: qsTr("%1  /  %2  /  Updated %3").arg(mode).arg(step).arg(updatedAt)
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }

                    ColumnLayout {
                        Layout.preferredWidth: 180
                        spacing: 7

                        RowLayout {
                            Layout.fillWidth: true

                            StatusPill {
                                status: jobDelegate.status
                                label: jobDelegate.status
                            }

                            Text {
                                Layout.fillWidth: true
                                text: qsTr("%1%").arg(progress)
                                color: Theme.textMuted
                                font.pixelSize: Theme.caption
                                horizontalAlignment: Text.AlignRight
                                textFormat: Text.PlainText
                            }
                        }

                        AppProgressBar {
                            Layout.fillWidth: true
                            value: progress
                        }
                    }

                    Text {
                        text: ">"
                        color: Theme.textSubtle
                        font.pixelSize: Theme.body
                        textFormat: Text.PlainText
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }
    }
}
