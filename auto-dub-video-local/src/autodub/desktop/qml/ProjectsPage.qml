import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

ColumnLayout {
    id: root

    signal requestNewProject()
    signal openProject()

    spacing: Theme.gap

    PageHeader {
        Layout.fillWidth: true
        title: I18n.t("Projects")
        subtitle: I18n.t("Create a project or reopen previous work.")

        AppButton {
            text: I18n.t("New project")
            tone: "primary"
            onClicked: root.requestNewProject()
        }
    }

    Panel {
        Layout.fillWidth: true
        Layout.fillHeight: true
        title: I18n.t("Recent projects")
        subtitle: I18n.t("Select a project to inspect its job and output.")

        Flickable {
            id: projectFlick
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: projectFlow.height

            Flow {
                id: projectFlow
                width: projectFlick.width
                height: childrenRect.height
                spacing: 14

                Rectangle {
                    width: 224
                    height: 190
                    radius: Theme.radius
                    color: newProjectHover.hovered ? Theme.interactiveMuted : Theme.surfaceElevated
                    border.width: 1
                    border.color: newProjectHover.hovered ? Theme.interactive : Theme.outline

                    HoverHandler {
                        id: newProjectHover
                        cursorShape: Qt.PointingHandCursor
                    }

                    TapHandler {
                        onTapped: root.requestNewProject()
                    }

                    Column {
                        anchors.centerIn: parent
                        spacing: 10

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 42
                            height: 42
                            radius: 21
                            color: Theme.interactiveMuted
                            border.width: 1
                            border.color: Theme.interactive

                            Text {
                                anchors.centerIn: parent
                                text: "+"
                                color: Theme.interactive
                                font.pixelSize: Theme.h2
                                textFormat: Text.PlainText
                            }
                        }

                        Text {
                            text: I18n.t("New project")
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.Medium
                            textFormat: Text.PlainText
                        }
                    }
                }

                Repeater {
                    model: controller.jobModel

                    delegate: ProjectCard {
                        onActivated: {
                            controller.selectJob(index)
                            root.openProject()
                        }
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {}
        }
    }
}
