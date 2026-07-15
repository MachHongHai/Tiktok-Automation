import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: root

    width: 1440
    height: 900
    minimumWidth: 1120
    minimumHeight: 720
    visible: true
    visibility: Window.Maximized
    title: I18n.t("Video Dubbing")
    color: Theme.window

    property int pageIndex: 0
    property int workspaceReturnPage: 0
    readonly property bool compactNavigation: width < 1280
    readonly property bool modelStatusFailed: controller.statusMessage.toLowerCase().indexOf("unavailable") >= 0
        || controller.statusMessage.toLowerCase().indexOf("failed") >= 0
    readonly property bool modelStatusBusy: !modelStatusFailed
        && controller.statusMessage.toLowerCase().indexOf("ready") < 0

    Component.onCompleted: {
        Theme.darkMode = controller.settingsTheme === "dark"
        I18n.language = controller.settingsLanguage
    }

    Shortcut {
        sequence: "Ctrl+,"
        onActivated: settingsDialog.open()
    }

    PreviewWindow {
        id: previewWindow
        transientParent: root
        onBatchSetupReturnRequested: batchSettingsDialog.open()
    }

    ProjectSetupDialog {
        id: projectSetupDialog
    }

    UrlImportDialog {
        id: urlImportDialog
    }

    SettingsDialog {
        id: settingsDialog
    }

    BatchSettingsDialog {
        id: batchSettingsDialog

        onRequestEditAllSubtitles: {
            close()
            previewWindow.returnToBatchSetup = true
            controller.openBatchSubtitleEditor()
        }

        onRequestEditSubtitleSize: function(sizeKey) {
            close()
            previewWindow.returnToBatchSetup = true
            controller.openBatchSizeEditor(sizeKey)
        }
    }

    TranslationReviewDialog {
        id: translationReviewDialog
    }

    Connections {
        target: controller

        function onPreviewOpenRequested() {
            previewWindow.openFromController()
        }

        function onJobDeleted() {
            root.pageIndex = root.workspaceReturnPage
        }

        function onBatchDeleted() {
            root.workspaceReturnPage = 0
            root.pageIndex = 0
        }

        function onSettingsChanged() {
            Theme.darkMode = controller.settingsTheme === "dark"
            I18n.language = controller.settingsLanguage
        }

        function onProjectPrepared() {
            root.workspaceReturnPage = 0
            root.pageIndex = controller.projectType === "batch" ? 2 : 1
        }
    }

    Overlay.modal: Rectangle {
        color: Theme.scrim
        Behavior on opacity {
            NumberAnimation { duration: Theme.motionStandard }
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: navigation

            Layout.preferredWidth: root.compactNavigation ? Theme.navigationCompact : Theme.navigationExpanded
            Layout.fillHeight: true
            color: Theme.sidebar

            Behavior on Layout.preferredWidth {
                NumberAnimation { duration: Theme.motionStandard; easing.type: Easing.OutCubic }
            }

            ColumnLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                anchors.topMargin: 16
                anchors.bottomMargin: 14
                spacing: 8

                Item {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 48

                    Row {
                        anchors.left: root.compactNavigation ? undefined : parent.left
                        anchors.horizontalCenter: root.compactNavigation ? parent.horizontalCenter : undefined
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 11

                        AppIcon {
                            width: 30
                            height: 30
                            glyph: "\uE714"
                            iconColor: Theme.interactive
                            iconSize: 22
                        }

                        Text {
                            visible: !root.compactNavigation
                            anchors.verticalCenter: parent.verticalCenter
                            text: I18n.t("Video Dubbing")
                            color: Theme.textOnDark
                            font.pixelSize: Theme.bodyLarge
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                        }
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    Layout.bottomMargin: 12
                    color: Theme.divider
                }

                Text {
                    visible: !root.compactNavigation
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.bottomMargin: 2
                    text: I18n.t("WORKSPACE")
                    color: Theme.textSubtle
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    font.capitalization: Font.AllUppercase
                    textFormat: Text.PlainText
                }

                SidebarButton {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    iconGlyph: "\uE8B7"
                    text: I18n.t("Projects")
                    selected: root.pageIndex === 0 || root.pageIndex === 1 || root.pageIndex === 2
                    onClicked: {
                        controller.refreshJobs()
                        root.pageIndex = 0
                    }
                }

                Item {
                    Layout.fillHeight: true
                }

                RowLayout {
                    visible: !root.compactNavigation && (root.modelStatusBusy || root.modelStatusFailed)
                    Layout.fillWidth: true
                    Layout.leftMargin: 12
                    Layout.rightMargin: 8
                    Layout.bottomMargin: 8
                    spacing: 9

                    Rectangle {
                        id: modelStatusIndicator
                        Layout.preferredWidth: 7
                        Layout.preferredHeight: 7
                        radius: 4
                        color: root.modelStatusFailed ? Theme.danger
                            : root.modelStatusBusy ? Theme.warning
                            : Theme.success

                        SequentialAnimation on opacity {
                            running: modelStatusIndicator.visible && root.modelStatusBusy && Theme.motionEnabled
                            loops: Animation.Infinite
                            NumberAnimation { to: 0.35; duration: 750; easing.type: Easing.InOutSine }
                            NumberAnimation { to: 1; duration: 750; easing.type: Easing.InOutSine }
                        }
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.runtimeStatus(controller.statusMessage)
                        color: Theme.textOnDarkMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    Layout.bottomMargin: 4
                    color: Theme.divider
                }

                SidebarButton {
                    Layout.fillWidth: true
                    compact: root.compactNavigation
                    iconGlyph: "\uE713"
                    text: I18n.t("Settings")
                    onClicked: settingsDialog.open()
                }
            }

            Rectangle {
                anchors.right: parent.right
                height: parent.height
                width: 1
                color: Theme.divider
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.pageIndex

                ProjectsPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: 24
                    Layout.bottomMargin: 24
                    onRequestNewProject: {
                        root.workspaceReturnPage = 0
                        projectSetupDialog.open()
                    }
                    onOpenProject: function(projectType) {
                        root.workspaceReturnPage = 0
                        root.pageIndex = projectType === "batch" ? 2 : 1
                    }
                }

                CreateJobPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 18 : 26
                    Layout.rightMargin: root.width < 1400 ? 18 : 26
                    Layout.topMargin: 20
                    Layout.bottomMargin: 20
                    onRequestReviewTranslation: translationReviewDialog.open()
                    onRequestBack: root.pageIndex = root.workspaceReturnPage
                    onRequestUrlImport: urlImportDialog.openForMode("single")
                }

                BatchPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.leftMargin: root.width < 1400 ? 22 : 30
                    Layout.rightMargin: root.width < 1400 ? 22 : 30
                    Layout.topMargin: root.width < 1400 ? 30 : 36
                    Layout.bottomMargin: 24
                    onRequestBack: root.pageIndex = 0
                    onRequestBatchSettings: batchSettingsDialog.open()
                    onRequestUrlImport: urlImportDialog.openForMode("batch")
                    onOpenJobDetail: {
                        root.workspaceReturnPage = 2
                        root.pageIndex = 1
                    }
                }
            }
        }
    }
}
