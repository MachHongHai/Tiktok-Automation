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
    title: qsTr("Auto Dub Studio")
    color: Theme.window

    property int pageIndex: 0
    property int detailReturnPage: 2
    readonly property string pageTitle: pageIndex === 0 ? qsTr("Create")
        : pageIndex === 1 ? qsTr("Batch")
        : pageIndex === 2 ? qsTr("Jobs")
        : qsTr("Job Detail")

    PreviewWindow {
        id: previewWindow
    }

    Connections {
        target: controller

        function onPreviewOpenRequested() {
            previewWindow.openFromController()
        }

        function onJobDeleted() {
            root.pageIndex = root.detailReturnPage
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

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 54
                    spacing: 11

                    Rectangle {
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        radius: 8
                        color: Theme.interactive

                        Text {
                            anchors.centerIn: parent
                            text: "AD"
                            color: Theme.sidebar
                            font.pixelSize: Theme.caption
                            font.weight: Font.Bold
                            textFormat: Text.PlainText
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 1

                        Text {
                            Layout.fillWidth: true
                            text: qsTr("Auto Dub")
                            color: Theme.textOnDark
                            font.pixelSize: Theme.h2
                            font.weight: Font.Medium
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }

                        Text {
                            Layout.fillWidth: true
                            text: qsTr("PRODUCTION STUDIO")
                            color: Theme.interactive
                            font.pixelSize: 10
                            font.weight: Font.DemiBold
                            textFormat: Text.PlainText
                            elide: Text.ElideRight
                        }
                    }
                }

                Text {
                    Layout.fillWidth: true
                    Layout.topMargin: 12
                    Layout.leftMargin: 8
                    text: qsTr("WORKSPACE")
                    color: Theme.textSubtle
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                SidebarButton {
                    Layout.fillWidth: true
                    marker: "+"
                    text: qsTr("Create")
                    selected: root.pageIndex === 0
                    onClicked: root.pageIndex = 0
                }

                SidebarButton {
                    Layout.fillWidth: true
                    marker: "B"
                    text: qsTr("Batch")
                    selected: root.pageIndex === 1 || (root.pageIndex === 3 && root.detailReturnPage === 1)
                    onClicked: root.pageIndex = 1
                }

                SidebarButton {
                    Layout.fillWidth: true
                    marker: "J"
                    text: qsTr("Jobs")
                    selected: root.pageIndex === 2 || (root.pageIndex === 3 && root.detailReturnPage === 2)
                    onClicked: {
                        controller.refreshJobs()
                        root.pageIndex = 2
                    }
                }

                Item {
                    Layout.fillHeight: true
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

                CreateJobPage {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.margins: 24
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
            }
        }
    }
}
