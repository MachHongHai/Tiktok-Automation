import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ApplicationWindow {
    id: root

    width: 1440
    height: 900
    minimumWidth: 1160
    minimumHeight: 760
    visible: true
    visibility: Window.Maximized
    title: qsTr("Video Dubbing")
    color: Theme.window

    property int pageIndex: 0
    property int detailReturnPage: 2
    readonly property string pageTitle: pageIndex === 0 ? I18n.t("Projects")
        : pageIndex === 1 ? I18n.t("Batch")
        : pageIndex === 2 ? I18n.t("Jobs")
        : pageIndex === 3 ? I18n.t("Job Detail")
        : I18n.t("Workspace")

    Component.onCompleted: {
        Theme.darkMode = controller.settingsTheme === "dark"
        I18n.language = controller.settingsLanguage
    }

    PreviewWindow {
        id: previewWindow
    }

    ProjectSetupDialog {
        id: projectSetupDialog
    }

    SettingsDialog {
        id: settingsDialog
    }

    Connections {
        target: controller

        function onPreviewOpenRequested() {
            previewWindow.openFromController()
        }

        function onJobDeleted() {
            root.pageIndex = root.detailReturnPage
        }

        function onSettingsChanged() {
            Theme.darkMode = controller.settingsTheme === "dark"
            I18n.language = controller.settingsLanguage
        }

        function onProjectPrepared() {
            root.pageIndex = 4
        }
    }

    RowLayout {
        anchors.fill: parent
        spacing: 0

        Rectangle {
            Layout.preferredWidth: 226
            Layout.fillHeight: true
            color: Theme.sidebar

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 16
                spacing: 12

                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 18
                    Layout.leftMargin: 8
                    text: I18n.t("WORKSPACE")
                    color: Theme.textSubtle
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                SidebarButton {
                    Layout.fillWidth: true
                    text: I18n.t("Projects")
                    selected: root.pageIndex === 0 || root.pageIndex === 4
                    onClicked: {
                        controller.refreshJobs()
                        root.pageIndex = 0
                    }
                }

                SidebarButton {
                    Layout.fillWidth: true
                    text: I18n.t("Batch")
                    selected: root.pageIndex === 1 || (root.pageIndex === 3 && root.detailReturnPage === 1)
                    onClicked: root.pageIndex = 1
                }

                SidebarButton {
                    Layout.fillWidth: true
                    text: I18n.t("Jobs")
                    selected: root.pageIndex === 2 || (root.pageIndex === 3 && root.detailReturnPage === 2)
                    onClicked: {
                        controller.refreshJobs()
                        root.pageIndex = 2
                    }
                }

                Item {
                    Layout.fillHeight: true
                }

                SidebarButton {
                    Layout.fillWidth: true
                    text: I18n.t("Settings")
                    onClicked: settingsDialog.open()
                }
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: Theme.window
                border.width: 0

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 26
                    anchors.rightMargin: 26
                    spacing: 12

                    Text {
                        Layout.fillWidth: true
                        text: root.pageTitle
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        font.weight: Font.Medium
                        textFormat: Text.PlainText
                    }

                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: Theme.outline
                }
            }

            StackLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                currentIndex: root.pageIndex

                ProjectsPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 24
                    onRequestNewProject: projectSetupDialog.open()
                    onOpenProject: {
                        root.detailReturnPage = 0
                        root.pageIndex = 3
                    }
                }

                BatchPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 24
                    onOpenJobDetail: {
                        root.detailReturnPage = 1
                        root.pageIndex = 3
                    }
                }

                JobsPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 24
                    onOpenJobDetail: {
                        root.detailReturnPage = 2
                        root.pageIndex = 3
                    }
                }

                JobDetailPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 24
                    onBackToJobs: root.pageIndex = root.detailReturnPage
                }

                CreateJobPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 24
                }

            }
        }
    }
}
