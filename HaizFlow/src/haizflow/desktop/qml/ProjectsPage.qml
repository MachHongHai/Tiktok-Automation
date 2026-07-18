pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property string projectType: "single"
    property var projectModel: null
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
            title: root.projectType === "batch"
                ? I18n.t("Batch projects")
                : I18n.t("Single projects")
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
                onClicked: AppController.refreshVideos()
            }
        }

        GridView {
            id: projectGrid

            readonly property int columnCount: Math.max(1, Math.floor((width + Theme.space16) / 270))
            readonly property real cardWidth: Math.min(320, Math.floor(
                (width - (columnCount - 1) * Theme.space16) / columnCount))
            readonly property real cardHeight: Math.round(cardWidth * 0.58 + 82)

            Layout.fillWidth: true
            Layout.fillHeight: true
            model: root.projectModel
            cellWidth: cardWidth + Theme.space16
            cellHeight: cardHeight + Theme.space16
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            reuseItems: true

            header: Item {
                width: projectGrid.width
                height: projectGrid.cardHeight + Theme.space16

                Rectangle {
                    id: newProjectCard

                    width: projectGrid.cardWidth
                    height: projectGrid.cardHeight
                    radius: Theme.radius
                    color: newProjectHover.hovered ? Theme.interactiveMuted : Theme.surfaceElevated
                    border.width: activeFocus ? 2 : 1
                    border.color: activeFocus || newProjectHover.hovered ? Theme.focus : Theme.outline
                    activeFocusOnTab: true
                    Accessible.role: Accessible.Button
                    Accessible.name: root.projectType === "batch"
                        ? I18n.t("New batch project")
                        : I18n.t("New single project")
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
                            text: root.projectType === "batch"
                                ? I18n.t("New batch project")
                                : I18n.t("New single project")
                            color: Theme.text
                            font.pixelSize: Theme.bodyLarge
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignHCenter
                            textFormat: Text.PlainText
                        }

                        Text {
                            width: parent.width
                            text: root.projectType === "batch"
                                ? I18n.t("Files, folders, links, or channels")
                                : I18n.t("One source video per project")
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
            }

            delegate: ProjectCard {
                width: projectGrid.cardWidth
                onActivated: {
                    AppController.selectProjectInMode(index, root.projectType)
                    root.openProject(root.projectType)
                }
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }
    }
}
