pragma ComponentBehavior: Bound
import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    objectName: "translationReviewDialog"

    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(980, parent ? parent.width - 64 : 980)
    height: Math.min(740, parent ? parent.height - 64 : 740)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    padding: 0
    title: I18n.t("Review translation")
    closePolicy: Popup.CloseOnEscape
    header: null
    footer: null

    property var segments: []

    function formatTime(secondsValue) {
        var total = Math.max(0, Math.floor(Number(secondsValue) || 0))
        var minutes = Math.floor(total / 60)
        var seconds = total % 60
        return String(minutes).padStart(2, "0") + ":" + String(seconds).padStart(2, "0")
    }

    onOpened: segments = JSON.parse(JSON.stringify(controller.reviewSegments))

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation { property: "scale"; from: 0.985; to: 1; duration: Theme.motionStandard; easing.type: Easing.OutCubic }
        }
    }
    exit: Transition {
        NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
    }

    background: Rectangle {
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
        radius: Theme.radius
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 70
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Review translation")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: qsTr("%1 %2").arg(root.segments.length).arg(I18n.t("segments"))
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: I18n.t("Close")
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space24
            Layout.topMargin: Theme.space16
            Layout.bottomMargin: Theme.space16
            radius: Theme.radius
            color: Theme.surfaceElevated
            border.width: 1
            border.color: Theme.outline

            ListView {
                id: segmentList
                anchors.fill: parent
                anchors.margins: 8
                clip: true
                model: root.segments
                spacing: 0
                reuseItems: true

                delegate: Item {
                    id: segmentRow
                    required property int index
                    required property var modelData

                    width: ListView.view.width
                    height: editorColumn.implicitHeight + 24

                    RowLayout {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.top: parent.top
                        anchors.bottom: divider.top
                        anchors.leftMargin: 10
                        anchors.rightMargin: 10
                        spacing: Theme.space16

                        Text {
                            Layout.preferredWidth: 34
                            Layout.alignment: Qt.AlignTop
                            Layout.topMargin: 27
                            text: String(segmentRow.index + 1).padStart(2, "0")
                            color: Theme.textSubtle
                            font.pixelSize: Theme.caption
                            font.weight: Font.DemiBold
                            horizontalAlignment: Text.AlignRight
                            textFormat: Text.PlainText
                        }

                        ColumnLayout {
                            id: editorColumn
                            Layout.fillWidth: true
                            Layout.topMargin: 10
                            Layout.bottomMargin: 12
                            spacing: 6

                            Text {
                                Layout.fillWidth: true
                                text: root.formatTime(segmentRow.modelData.start)
                                    + "  -  " + root.formatTime(segmentRow.modelData.end)
                                color: Theme.textMuted
                                font.pixelSize: Theme.label
                                font.weight: Font.Medium
                                textFormat: Text.PlainText
                            }

                            TextArea {
                                id: translationEditor
                                Layout.fillWidth: true
                                Layout.preferredHeight: Math.min(96, Math.max(52, contentHeight + 18))
                                text: segmentRow.modelData.text || ""
                                wrapMode: TextEdit.Wrap
                                color: Theme.text
                                font.pixelSize: Theme.body
                                selectByMouse: true
                                activeFocusOnTab: true
                                Accessible.name: qsTr("Segment %1").arg(segmentRow.index + 1)
                                background: Rectangle {
                                    color: Theme.input
                                    border.width: translationEditor.activeFocus ? 2 : 1
                                    border.color: translationEditor.activeFocus ? Theme.focus : Theme.outline
                                    radius: Theme.radiusSmall
                                }
                                onTextChanged: {
                                    if (root.segments[segmentRow.index])
                                        root.segments[segmentRow.index].text = text
                                }
                            }
                        }
                    }

                    Rectangle {
                        id: divider
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.bottom: parent.bottom
                        height: segmentRow.index === segmentList.count - 1 ? 0 : 1
                        color: Theme.divider
                    }
                }

                ScrollBar.vertical: ScrollBar {
                    policy: ScrollBar.AsNeeded
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 74
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space24
            spacing: Theme.space8

            Item { Layout.fillWidth: true }

            AppButton {
                text: I18n.t("Cancel")
                tone: "ghost"
                onClicked: root.close()
            }

            AppButton {
                text: I18n.t("Approve and continue")
                iconGlyph: "\uE73E"
                tone: "primary"
                enabled: root.segments.length > 0
                onClicked: {
                    controller.approveTranslationReview(JSON.stringify(root.segments))
                    root.close()
                }
            }
        }
    }
}
