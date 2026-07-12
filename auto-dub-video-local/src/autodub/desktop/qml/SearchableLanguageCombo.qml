import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    property var options: []
    property var filteredModel: options
    property string selectedCode: ""
    property string placeholderText: qsTr("Search language")
    property bool interactionActive: false
    signal selected(string code)

    implicitHeight: field.implicitHeight

    function labelFor(code) {
        for (var i = 0; i < options.length; i++) {
            if (options[i].code === code) {
                return options[i].label
            }
        }
        return code
    }

    function filteredOptions(queryText) {
        var query = queryText.toLowerCase().trim()
        if (query.length === 0 || queryText === root.labelFor(root.selectedCode)) {
            return options
        }
        var result = []
        for (var i = 0; i < options.length; i++) {
            if (options[i].search.indexOf(query) !== -1) {
                result.push(options[i])
            }
        }
        return result
    }

    function refreshFilter() {
        filteredModel = filteredOptions(field.text + (field.inputMethodComposing ? field.preeditText : ""))
    }

    onOptionsChanged: refreshFilter()

    TextField {
        id: field
        anchors.fill: parent
        placeholderText: root.placeholderText
        selectByMouse: true
        color: Theme.text
        placeholderTextColor: Theme.textMuted
        font.pixelSize: Theme.body
        leftPadding: 12
        rightPadding: 38
        verticalAlignment: TextInput.AlignVCenter
        background: Rectangle {
            color: field.hovered ? Theme.surfaceStrong : Theme.surfaceElevated
            radius: Theme.radiusSmall
            border.width: 1
            border.color: field.activeFocus ? Theme.interactive : Theme.outline
        }

        Text {
            anchors.right: parent.right
            anchors.rightMargin: 13
            anchors.verticalCenter: parent.verticalCenter
            text: "v"
            color: Theme.textMuted
            font.pixelSize: Theme.caption
            textFormat: Text.PlainText
        }
        onTextChanged: {
            root.refreshFilter()
            if (root.interactionActive && !popup.opened) {
                popup.open()
            }
        }
        onPreeditTextChanged: root.refreshFilter()

        Keys.onPressed: {
            if (!root.interactionActive) {
                root.interactionActive = true
                field.selectAll()
            }
            if (!popup.opened) {
                popup.open()
            }
        }

        TapHandler {
            acceptedButtons: Qt.LeftButton
            onTapped: {
                root.interactionActive = true
                field.forceActiveFocus()
                field.selectAll()
                popup.open()
            }
        }

        Binding {
            target: field
            property: "text"
            value: root.labelFor(root.selectedCode)
            when: !field.activeFocus
        }
    }

    Popup {
        id: popup
        objectName: "languageSearchPopup"
        y: field.height + 4
        width: field.width
        height: Math.min(320, Math.max(72, list.contentHeight + 12))
        padding: 6
        modal: false
        focus: false
        z: 100
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        onOpened: root.refreshFilter()
        onClosed: {
            root.interactionActive = false
            field.text = root.labelFor(root.selectedCode)
        }

        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.color: Theme.outlineStrong
            border.width: 1
        }

        ListView {
            id: list
            anchors.fill: parent
            clip: true
            model: root.filteredModel

            delegate: Item {
                id: row
                readonly property var option: modelData

                width: ListView.view.width
                height: 42

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusSmall
                    color: row.option && (row.option.code === root.selectedCode || mouseArea.containsMouse)
                           ? Theme.interactiveMuted : "#00000000"
                }

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    text: row.option ? row.option.label : ""
                    color: row.option && row.option.code === root.selectedCode ? Theme.interactive : Theme.text
                    font.pixelSize: Theme.body
                    font.weight: row.option && row.option.code === root.selectedCode ? Font.Medium : Font.Normal
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                }

                MouseArea {
                    id: mouseArea
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        if (row.option) {
                            root.selected(row.option.code)
                        }
                        popup.close()
                    }
                }
            }
        }
    }
}
