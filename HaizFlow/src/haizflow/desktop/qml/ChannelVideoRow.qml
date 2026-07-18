pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts
import "."

Rectangle {
    id: root

    required property int index
    required property string candidateId
    required property bool selected
    required property string title
    required property string platform
    required property string uploader
    required property string durationLabel
    required property string publishedLabel
    required property string viewCountLabel
    required property string thumbnailSource
    required property bool duplicate
    required property string candidateStatus
    required property int candidateProgress
    required property string candidateError

    signal selectionChanged(bool selected)
    signal retryRequested()

    readonly property bool locked: duplicate
        || candidateStatus === "downloading"
        || candidateStatus === "importing"
        || candidateStatus === "imported"

    function statusLabel() {
        if (duplicate)
            return I18n.t("Already in project")
        switch (candidateStatus) {
        case "downloading": return I18n.t("Downloading")
        case "importing": return I18n.t("Adding to project")
        case "imported": return I18n.t("Imported")
        case "failed": return I18n.t("Failed")
        default: return I18n.t("Ready")
        }
    }

    implicitHeight: 92
    radius: Theme.radiusSmall
    color: rowHover.hovered ? Theme.surfaceMuted : "transparent"

    HoverHandler {
        id: rowHover
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: Theme.space12
        anchors.rightMargin: Theme.space12
        anchors.topMargin: Theme.space8
        anchors.bottomMargin: Theme.space8
        spacing: Theme.space12

        AppCheckBox {
            Layout.preferredWidth: 24
            Layout.alignment: Qt.AlignVCenter
            checked: root.selected
            enabled: !root.locked
            text: ""
            Accessible.name: I18n.t("Select video") + ": " + root.title
            onToggled: root.selectionChanged(checked)
        }

        Rectangle {
            Layout.preferredWidth: 112
            Layout.preferredHeight: 64
            radius: Theme.radiusTiny
            color: Theme.surfaceStrong
            clip: true

            Image {
                anchors.fill: parent
                source: root.thumbnailSource
                sourceSize.width: 224
                sourceSize.height: 128
                asynchronous: true
                cache: true
                fillMode: Image.PreserveAspectCrop
            }

            Text {
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 5
                text: root.durationLabel
                color: "white"
                font.pixelSize: Theme.label
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                style: Text.Outline
                styleColor: "#88000000"
            }
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.space4

            Text {
                Layout.fillWidth: true
                text: root.title
                color: root.duplicate ? Theme.textMuted : Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                textFormat: Text.PlainText
                elide: Text.ElideRight
                maximumLineCount: 1
            }

            Text {
                Layout.fillWidth: true
                text: [root.uploader, root.publishedLabel].filter(function(value) {
                    return value.length > 0
                }).join(" | ")
                color: Theme.textMuted
                font.pixelSize: Theme.caption
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }

            AppProgressBar {
                Layout.fillWidth: true
                Layout.maximumWidth: 360
                visible: root.candidateStatus === "downloading" || root.candidateStatus === "importing"
                value: root.candidateProgress
            }

            Text {
                Layout.fillWidth: true
                visible: root.candidateError.length > 0
                text: I18n.channelImportStatus(root.candidateError)
                color: Theme.danger
                font.pixelSize: Theme.label
                textFormat: Text.PlainText
                elide: Text.ElideRight
            }
        }

        ColumnLayout {
            Layout.preferredWidth: 104
            Layout.alignment: Qt.AlignVCenter
            spacing: Theme.space4

            Text {
                Layout.fillWidth: true
                text: I18n.t("Views")
                color: Theme.textSubtle
                font.pixelSize: Theme.label
                horizontalAlignment: Text.AlignRight
                textFormat: Text.PlainText
            }

            Text {
                Layout.fillWidth: true
                text: root.viewCountLabel
                color: Theme.text
                font.pixelSize: Theme.body
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignRight
                textFormat: Text.PlainText
            }
        }

        Item {
            Layout.preferredWidth: 180
            Layout.preferredHeight: 40

            StatusPill {
                anchors.centerIn: parent
                visible: root.candidateStatus !== "failed"
                status: root.candidateStatus === "imported" ? "done"
                    : root.candidateStatus === "downloading" || root.candidateStatus === "importing" ? "processing"
                    : root.duplicate ? "cancelled"
                    : "pending"
                label: root.statusLabel()
            }

            AppButton {
                anchors.fill: parent
                visible: root.candidateStatus === "failed"
                text: I18n.t("Retry")
                iconGlyph: "\uE72C"
                tone: "secondary"
                onClicked: root.retryRequested()
            }
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.divider
    }

    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }
}
