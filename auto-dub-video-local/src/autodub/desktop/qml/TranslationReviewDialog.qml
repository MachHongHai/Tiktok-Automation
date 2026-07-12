import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Dialog {
    id: root
    modal: true
    focus: true
    parent: Overlay.overlay
    width: Math.min(760, parent.width - 80)
    height: Math.min(680, parent.height - 80)
    x: Math.round((parent.width - width) / 2)
    y: Math.round((parent.height - height) / 2)
    title: qsTr("Review translation")
    property var segments: []

    onOpened: segments = JSON.parse(JSON.stringify(controller.reviewSegments))

    background: Rectangle { color: Theme.surface; border.width: 1; border.color: Theme.outlineStrong; radius: Theme.radius }
    contentItem: ColumnLayout {
        spacing: 14
        Text { Layout.fillWidth: true; text: qsTr("Review translation"); color: Theme.text; font.pixelSize: Theme.h2; font.weight: Font.Medium }
        ListView {
            id: list
            Layout.fillWidth: true
            Layout.fillHeight: true
            clip: true
            model: root.segments
            spacing: 8
            delegate: ColumnLayout {
                required property int index
                required property var modelData
                width: list.width
                spacing: 3
                Text { text: qsTr("Segment %1").arg(index + 1); color: Theme.textMuted; font.pixelSize: Theme.caption }
                TextArea {
                    Layout.fillWidth: true
                    implicitHeight: 58
                    text: modelData.text || ""
                    wrapMode: TextEdit.Wrap
                    color: Theme.text
                    onTextChanged: root.segments[index].text = text
                    background: Rectangle { color: Theme.surfaceElevated; border.width: 1; border.color: Theme.outline; radius: Theme.radiusSmall }
                }
            }
            ScrollBar.vertical: ScrollBar {}
        }
        RowLayout {
            Layout.fillWidth: true
            Item { Layout.fillWidth: true }
            AppButton { text: I18n.t("Cancel"); tone: "ghost"; onClicked: root.close() }
            AppButton { text: qsTr("Approve and continue"); tone: "primary"; onClicked: { controller.approveTranslationReview(JSON.stringify(root.segments)); root.close() } }
        }
    }
}
