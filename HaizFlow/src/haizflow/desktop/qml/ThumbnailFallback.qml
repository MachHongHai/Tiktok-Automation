import QtQuick
import "."

Item {
    id: root

    property string label: I18n.t("No preview")

    Column {
        anchors.centerIn: parent
        spacing: Theme.space8

        AppIcon {
            anchors.horizontalCenter: parent.horizontalCenter
            width: 28
            height: 28
            glyph: "\uE714"
            iconColor: Theme.textSubtle
            iconSize: Theme.iconLarge
        }

        Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: root.label
            color: Theme.textSubtle
            font.pixelSize: Theme.caption
            textFormat: Text.PlainText
        }
    }
}
