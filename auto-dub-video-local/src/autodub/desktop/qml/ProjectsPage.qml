pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestNewProject()
    signal openProject(string projectType)

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
        spacing: Theme.space20

        PageHeader {
            Layout.fillWidth: true
            title: I18n.t("Projects")
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: Theme.space12

            Text {
                Layout.fillWidth: true
                text: I18n.t("Recent projects")
                color: Theme.text
                font.pixelSize: Theme.h2
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
            }

            IconButton {
                glyph: "\uE72C"
                toolTipText: I18n.t("Refresh")
                onClicked: controller.refreshJobs()
            }
        }

        Flickable {
            id: projectFlick

            readonly property int columnCount: Math.max(2, Math.floor((width + projectFlow.spacing) / 270))
            readonly property real cardWidth: Math.min(320, Math.floor((width - (columnCount - 1) * projectFlow.spacing) / columnCount))

            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            contentWidth: width
            contentHeight: projectFlow.height + 8
            boundsBehavior: Flickable.StopAtBounds

            Flow {
                id: projectFlow
                width: projectFlick.width
                height: childrenRect.height
                spacing: Theme.space16

                Rectangle {
                    id: newProjectCard

                    width: projectFlick.cardWidth
                    height: Math.round(width * 0.58 + 82)
                    radius: Theme.radius
                    color: newProjectHover.hovered ? Theme.interactiveMuted : Theme.surfaceElevated
                    border.width: activeFocus ? 2 : 1
                    border.color: activeFocus || newProjectHover.hovered ? Theme.focus : Theme.outline
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: I18n.t("New project")
                    scale: newProjectTap.pressed ? 0.99 : 1

                    Keys.onReturnPressed: root.requestNewProject()
                    Keys.onSpacePressed: root.requestNewProject()

                    HoverHandler {
                        id: newProjectHover
                        cursorShape: Qt.PointingHandCursor
                    }

                    TapHandler {
                        id: newProjectTap
                        onTapped: {
                            newProjectCard.forceActiveFocus()
                            root.requestNewProject()
                        }
                    }

                    Column {
                        anchors.centerIn: parent
                        width: Math.min(parent.width - 40, 230)
                        spacing: Theme.space12

                        Rectangle {
                            anchors.horizontalCenter: parent.horizontalCenter
                            width: 44
                            height: 44
                            radius: 22
                            color: Theme.interactive

                            AppIcon {
                                anchors.centerIn: parent
                                width: 20
                                height: 20
                                glyph: "\uE710"
                                iconColor: Theme.textOnAccent
                                iconSize: Theme.icon
                            }
                        }

                        Text {
                            width: parent.width
                            text: I18n.t("New project")
                            color: Theme.text
                            font.pixelSize: Theme.bodyLarge
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                        }

                        Text {
                            width: parent.width
                            text: I18n.t("Single video or batch")
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                        }
                    }

                    Behavior on color {
                        ColorAnimation { duration: Theme.motionFast }
                    }
                    Behavior on scale {
                        NumberAnimation { duration: Theme.motionFast; easing.type: Easing.OutCubic }
                    }
                }

                Repeater {
                    model: controller.projectModel

                    delegate: ProjectCard {
                        width: projectFlick.cardWidth
                        onActivated: {
                            controller.selectProject(index)
                            root.openProject(projectType)
                        }
                    }
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }
    }
}
