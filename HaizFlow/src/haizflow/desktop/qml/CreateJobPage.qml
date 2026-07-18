import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestReviewTranslation()
    signal requestBack()
    signal requestUrlImport()

    readonly property bool wideLayout: width >= 1380

    opacity: visible ? 1 : 0
    transform: Translate {
        y: root.visible ? 0 : 8
        Behavior on y {
            NumberAnimation { duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }
    Behavior on opacity {
        NumberAnimation { duration: Theme.motionStandard }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            AppButton {
                text: I18n.t("Back")
                iconGlyph: "\uE72B"
                tone: "secondary"
                onClicked: {
                    if (controller.isSelectedBatchJob && !controller.isSelectedJobProcessing)
                        controller.saveSelectedJobSettings()
                    root.requestBack()
                }
            }

            PageHeader {
                Layout.fillWidth: true
                title: controller.projectName || controller.selectedFileName || I18n.t("Create a new dub")
                subtitle: controller.projectDirectory || I18n.t("Turn one source video into a translated, voiced and captioned export.")
            }
        }

        ScrollView {
            id: workspaceScroll

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            ScrollBar.vertical.policy: ScrollBar.AsNeeded

            GridLayout {
                id: workspaceGrid

                width: workspaceScroll.availableWidth
                height: root.wideLayout ? Math.max(implicitHeight, workspaceScroll.availableHeight) : implicitHeight
                columns: root.wideLayout ? 3 : 2
                columnSpacing: Theme.space16
                rowSpacing: Theme.space16

                SourceMediaPanel {
                    Layout.row: 0
                    Layout.column: 0
                    Layout.fillWidth: true
                    Layout.fillHeight: root.wideLayout
                    Layout.minimumWidth: 390
                    Layout.preferredWidth: root.wideLayout ? 440 : 480
                    Layout.preferredHeight: 536
                    onRequestUrlImport: root.requestUrlImport()
                }

                DubbingSetupPanel {
                    Layout.row: 0
                    Layout.column: 1
                    Layout.fillWidth: true
                    Layout.fillHeight: root.wideLayout
                    Layout.minimumWidth: 330
                    Layout.preferredWidth: root.wideLayout ? 370 : 440
                    Layout.preferredHeight: 536
                }

                ActivityLogPanel {
                    Layout.row: root.wideLayout ? 0 : 1
                    Layout.column: root.wideLayout ? 2 : 0
                    Layout.columnSpan: root.wideLayout ? 1 : 2
                    Layout.fillWidth: true
                    Layout.fillHeight: root.wideLayout
                    Layout.minimumWidth: root.wideLayout ? 390 : 0
                    Layout.preferredWidth: 540
                    Layout.preferredHeight: root.wideLayout ? 536 : 300
                }
            }
        }

        JobCommandBar {
            Layout.fillWidth: true
            onRequestReviewTranslation: root.requestReviewTranslation()
        }
    }
}
