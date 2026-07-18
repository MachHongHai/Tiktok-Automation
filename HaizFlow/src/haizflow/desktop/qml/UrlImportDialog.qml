import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    objectName: "urlImportDialog"

    property string importMode: "single"
    property string inspectedText: ""
    readonly property var importer: controller.urlImporter
    readonly property bool hasMetadata: importer.title.length > 0
    readonly property bool hasStatus: importer.status.length > 0
    readonly property bool showsProgress: importer.state === "downloading"
        || importer.state === "importing"

    function openForMode(mode) {
        importMode = mode === "batch" ? "batch" : "single"
        root.importer.begin(importMode)
        open()
    }

    modal: true
    focus: true
    width: Math.min(680, parent ? parent.width - 48 : 680)
    height: hasMetadata ? (showsProgress ? 500 : 470)
        : hasStatus ? 340
        : 300
    padding: 0
    title: I18n.t("Import from link")
    closePolicy: root.importer.busy ? Popup.NoAutoClose
        : Popup.CloseOnEscape | Popup.CloseOnPressOutside
    parent: Overlay.overlay
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    header: null
    footer: null

    onOpened: {
        videoUrl.clear()
        inspectedText = ""
        videoUrl.forceActiveFocus()
    }

    Connections {
        target: root.importer

        function onChanged() {
            if (root.importer.state === "ready" && root.inspectedText.length === 0)
                root.inspectedText = videoUrl.text.trim()
        }
    }

    Connections {
        target: controller

        function onUrlImportFinished() {
            if (root.opened)
                root.close()
        }
    }

    enter: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionStandard }
            NumberAnimation {
                property: "scale"
                from: 0.98
                to: 1
                duration: Theme.motionStandard
                easing.type: Easing.OutCubic
            }
        }
    }
    exit: Transition {
        ParallelAnimation {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
            NumberAnimation { property: "scale"; from: 1; to: 0.99; duration: Theme.motionFast }
        }
    }

    background: Rectangle {
        radius: Theme.radius
        color: Theme.surface
        border.width: 1
        border.color: Theme.outlineStrong
    }

    contentItem: ColumnLayout {
        spacing: 0

        RowLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 72
            Layout.leftMargin: Theme.space24
            Layout.rightMargin: Theme.space16
            spacing: Theme.space12

            AppIcon {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                glyph: "\uE71B"
                iconColor: Theme.interactive
                iconSize: Theme.iconLarge
            }

            ColumnLayout {
                Layout.fillWidth: true
                spacing: 2

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("Import from link")
                    color: Theme.text
                    font.pixelSize: Theme.h2
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.t("YouTube, TikTok or Douyin")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                }
            }

            IconButton {
                glyph: "\uE711"
                toolTipText: root.importer.busy ? I18n.t("Cancel download first") : I18n.t("Close")
                enabled: !root.importer.busy
                onClicked: root.close()
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 1
            color: Theme.divider
        }

        ColumnLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            Layout.margins: Theme.space24
            spacing: Theme.space16

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Text {
                    text: I18n.t("Video link")
                    color: Theme.textMuted
                    font.pixelSize: Theme.caption
                    font.weight: Font.Medium
                    textFormat: Text.PlainText
                }

                TextField {
                    id: videoUrl

                    Layout.fillWidth: true
                    implicitHeight: 46
                    enabled: !root.importer.busy
                    color: Theme.text
                    font.pixelSize: Theme.body
                    placeholderText: I18n.t("Paste a video link")
                    selectByMouse: true
                    activeFocusOnTab: true
                    Accessible.name: I18n.t("Video link")
                    leftPadding: 14
                    rightPadding: 14

                    onTextEdited: {
                        if (text.trim() !== root.inspectedText)
                            root.inspectedText = ""
                    }

                    Keys.onReturnPressed: {
                        if (!root.importer.busy && text.trim().length > 0) {
                            root.inspectedText = ""
                            root.importer.inspect(text.trim())
                        }
                    }

                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: Theme.input
                        border.width: videoUrl.activeFocus ? 2 : 1
                        border.color: videoUrl.activeFocus ? Theme.focus : Theme.outline
                    }
                }
            }

            Rectangle {
                id: metadataPanel

                Layout.fillWidth: true
                Layout.preferredHeight: 132
                visible: root.hasMetadata
                radius: Theme.radiusSmall
                color: Theme.surfaceElevated
                border.width: 1
                border.color: Theme.outline

                RowLayout {
                    anchors.fill: parent
                    anchors.margins: Theme.space12
                    spacing: Theme.space16

                    Rectangle {
                        Layout.preferredWidth: 176
                        Layout.preferredHeight: 99
                        radius: Theme.radiusTiny
                        color: Theme.video
                        clip: true

                        Image {
                            anchors.fill: parent
                            source: root.importer.thumbnailSource
                            sourceSize.width: 352
                            sourceSize.height: 198
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: true
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: Theme.space8

                        Text {
                            Layout.fillWidth: true
                            text: root.importer.title
                            color: Theme.text
                            font.pixelSize: Theme.body
                            font.weight: Font.DemiBold
                            maximumLineCount: 2
                            wrapMode: Text.Wrap
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }

                        Text {
                            Layout.fillWidth: true
                            text: root.importer.uploader
                            visible: text.length > 0
                            color: Theme.textMuted
                            font.pixelSize: Theme.caption
                            elide: Text.ElideRight
                            textFormat: Text.PlainText
                        }

                        Item { Layout.fillHeight: true }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: Theme.space8

                            StatusPill {
                                label: root.importer.platform
                                status: "awaiting_review"
                            }

                            Text {
                                text: root.importer.duration
                                visible: text.length > 0
                                color: Theme.textMuted
                                font.pixelSize: Theme.caption
                                textFormat: Text.PlainText
                            }
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                visible: root.importer.status.length > 0
                spacing: Theme.space8

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space8

                    AppIcon {
                        Layout.preferredWidth: 18
                        Layout.preferredHeight: 18
                        glyph: root.importer.state === "error" ? "\uEA39"
                            : root.importer.state === "ready" ? "\uE73E"
                            : "\uE895"
                        iconColor: root.importer.state === "error" ? Theme.danger
                            : root.importer.state === "ready" ? Theme.success
                            : Theme.interactive
                        iconSize: Theme.iconSmall
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t(root.importer.status)
                        color: root.importer.state === "error" ? Theme.danger : Theme.textMuted
                        font.pixelSize: Theme.caption
                        wrapMode: Text.Wrap
                        textFormat: Text.PlainText
                    }

                    Text {
                        visible: root.importer.state === "downloading"
                        text: qsTr("%1%").arg(root.importer.progress)
                        color: Theme.text
                        font.pixelSize: Theme.caption
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                    }
                }

                AppProgressBar {
                    Layout.fillWidth: true
                    visible: root.importer.state === "downloading"
                        || root.importer.state === "importing"
                    value: root.importer.progress
                }
            }

            Item { Layout.fillHeight: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space8

                Item { Layout.fillWidth: true }

                AppButton {
                    text: root.importer.busy ? I18n.t("Cancel download") : I18n.t("Cancel")
                    tone: root.importer.busy ? "danger" : "ghost"
                    onClicked: {
                        if (root.importer.busy)
                            root.importer.cancel()
                        else
                            root.close()
                    }
                }

                AppButton {
                    text: root.importer.state === "ready" && root.inspectedText.length > 0
                        ? I18n.t("Download and import")
                        : I18n.t("Check link")
                    iconGlyph: root.importer.state === "ready" && root.inspectedText.length > 0
                        ? "\uE896"
                        : "\uE721"
                    tone: "primary"
                    enabled: !root.importer.busy && videoUrl.text.trim().length > 0
                    onClicked: {
                        if (root.importer.state === "ready" && root.inspectedText.length > 0)
                            controller.downloadInspectedVideo()
                        else {
                            root.inspectedText = ""
                            root.importer.inspect(videoUrl.text.trim())
                        }
                    }
                }
            }
        }
    }
}
