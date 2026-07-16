import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    signal requestReviewTranslation()

    readonly property bool hasOutput: controller.hasSelectedOutput
    readonly property bool hasProject: controller.hasOpenProject
    readonly property bool selectedProcessing: controller.isSelectedJobProcessing
    readonly property bool canStart: controller.hasSelectedJob && controller.selectedStatus === "pending"
        && !controller.isSelectedJobQueued
    readonly property bool canRestart: controller.hasSelectedJob && !controller.isSelectedJobProcessing
        && !controller.isSelectedJobQueued
        && controller.selectedStatus !== "pending"
    readonly property string headline: root.selectedProcessing
        ? I18n.t(controller.selectedStageLabel)
        : controller.selectedProgress >= 100
            ? I18n.t("Last export ready")
            : controller.hasSelectedJob
                ? I18n.t(controller.selectedStageLabel)
                : I18n.t("Ready to process")

    implicitHeight: 116
    radius: Theme.radius
    color: Theme.surface
    border.width: 1
    border.color: Theme.outline

    RowLayout {
        anchors.fill: parent
        anchors.margins: Theme.space20
        spacing: Theme.space20

        Rectangle {
            Layout.preferredWidth: 38
            Layout.preferredHeight: 38
            radius: Theme.radiusSmall
            color: controller.selectedStatus === "done" ? Theme.successMuted
                : controller.selectedStatus === "failed" ? Theme.dangerMuted
                : root.selectedProcessing ? Theme.warningMuted
                : Theme.surfaceElevated

            AppIcon {
                anchors.centerIn: parent
                width: 20
                height: 20
                glyph: controller.selectedStatus === "done" ? "\uE73E"
                    : controller.selectedStatus === "failed" ? "\uEA39"
                    : root.selectedProcessing ? "\uE895"
                    : "\uE946"
                iconColor: controller.selectedStatus === "done" ? Theme.success
                    : controller.selectedStatus === "failed" ? Theme.danger
                    : root.selectedProcessing ? Theme.warning
                    : Theme.textMuted
                iconSize: Theme.icon
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.minimumWidth: 330
            spacing: 6

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space12

                Text {
                    Layout.fillWidth: true
                    text: root.headline
                    color: Theme.text
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                    elide: Text.ElideRight
                }

                Text {
                    text: qsTr("%1%").arg(controller.selectedProgress)
                    color: controller.selectedProgress >= 100 ? Theme.success : Theme.interactive
                    font.pixelSize: Theme.h3
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    visible: controller.selectedElapsed.length > 0
                    text: (controller.selectedStatus === "processing"
                        ? I18n.t("Time running")
                        : I18n.t("Processing time")) + " " + controller.selectedElapsed
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            Text {
                Layout.fillWidth: true
                text: I18n.progressDetail(controller.selectedProgressDetail
                    || controller.selectedStep
                    || "Processing status will appear here")
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

        RowLayout {
            spacing: Theme.space8

            AppButton {
                visible: controller.selectedStatus === "paused"
                text: I18n.t("Resume")
                iconGlyph: "\uE768"
                tone: "primary"
                onClicked: controller.resumeSelectedJob()
            }

            AppButton {
                visible: controller.selectedStatus === "awaiting_review"
                text: I18n.t("Review translation")
                iconGlyph: "\uE70F"
                tone: "primary"
                onClicked: root.requestReviewTranslation()
            }

            AppButton {
                visible: root.canStart
                text: I18n.t("Process")
                iconGlyph: "\uE768"
                tone: "primary"
                onClicked: controller.startProjectJob()
            }

            AppButton {
                visible: root.canRestart
                text: I18n.t("Restart")
                iconGlyph: "\uE72C"
                tone: "primary"
                onClicked: controller.restartSelectedJob()
            }

            AppButton {
                visible: root.selectedProcessing
                text: I18n.t("Pause")
                iconGlyph: "\uE769"
                tone: "danger"
                onClicked: controller.stopJob()
            }

            AppButton {
                visible: controller.hasSelectedJob
                text: I18n.t("Open output video")
                iconGlyph: "\uE768"
                tone: "primary"
                enabled: root.hasOutput
                onClicked: controller.openOutputFile()
            }

            AppButton {
                visible: root.hasProject && !controller.hasSelectedJob
                text: I18n.t("Open project folder")
                iconGlyph: "\uE8B7"
                tone: "secondary"
                onClicked: controller.openProjectFolder()
            }

            IconButton {
                id: moreButton
                visible: controller.hasSelectedJob || root.hasProject
                glyph: "\uE712"
                toolTipText: I18n.t("More actions")
                onClicked: jobMenu.open()

                Menu {
                    id: jobMenu
                    width: 242
                    y: -height - 8
                    padding: 6
                    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

                    enter: Transition {
                        NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionFast }
                    }
                    exit: Transition {
                        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
                    }

                    background: Rectangle {
                        color: Theme.surfaceElevated
                        radius: Theme.radius
                        border.width: 1
                        border.color: Theme.outlineStrong
                    }

                    AppMenuItem {
                        text: I18n.t("Open input video")
                        iconGlyph: "\uE714"
                        visible: controller.hasSelectedJob
                        onTriggered: controller.openInputFile()
                    }

                    AppMenuItem {
                        text: I18n.t("Open export folder")
                        iconGlyph: "\uE8B7"
                        visible: controller.hasSelectedJob
                        onTriggered: controller.openOutputFolder()
                    }

                    AppMenuItem {
                        text: I18n.t("Open project folder")
                        iconGlyph: "\uE8B7"
                        visible: root.hasProject
                        onTriggered: controller.openProjectFolder()
                    }

                    AppMenuItem {
                        visible: root.canRestart
                        text: I18n.t("Restart")
                        iconGlyph: "\uE72C"
                        onTriggered: controller.restartSelectedJob()
                    }

                    AppMenuItem {
                        text: I18n.t("Remove video")
                        iconGlyph: "\uE74D"
                        tone: "danger"
                        visible: controller.isSelectedBatchJob
                        onTriggered: controller.deleteSelectedJob()
                    }

                    AppMenuItem {
                        text: I18n.t("Delete project")
                        iconGlyph: "\uE74D"
                        tone: "danger"
                        // Batch deletion belongs to the batch-level action bar.
                        // An opened batch video can only remove that video here.
                        visible: root.hasProject && !controller.isSelectedBatchJob
                        onTriggered: controller.deleteCurrentProject()
                    }
                }
            }
        }
    }
}
