pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import "."

Item {
    id: root
    objectName: "targetLanguagePicker"

    property var options: []
    property var filteredModel: []
    property string selectedCode: ""
    property string placeholderText: I18n.t("Search language")
    property bool userEditing: false
    signal selected(string code)

    implicitHeight: 42

    function labelFor(code) {
        for (var i = 0; i < options.length; i++) {
            if (options[i].code === code)
                return options[i].label
        }
        return code
    }

    function indexFor(code, model) {
        var source = model || options
        for (var i = 0; i < source.length; i++) {
            if (source[i].code === code)
                return i
        }
        return source.length > 0 ? 0 : -1
    }

    function filterOptions(queryText) {
        var query = queryText.toLowerCase().trim()
        if (query.length === 0)
            return options

        var result = []
        for (var i = 0; i < options.length; i++) {
            if (options[i].search.indexOf(query) !== -1)
                result.push(options[i])
        }
        return result
    }

    function beginEditing() {
        if (!root.enabled)
            return

        if (!userEditing) {
            userEditing = true
            field.text = ""
            filteredModel = options
        }

        field.forceActiveFocus()
        if (!languagePopup.opened)
            languagePopup.open()
    }

    function finishEditing() {
        userEditing = false
        field.text = ""
        filteredModel = options
    }

    function focusLanguageList() {
        Qt.callLater(function() {
            if (!languagePopup.opened)
                return
            languageList.currentIndex = root.indexFor(root.selectedCode, root.filteredModel)
            languageList.forceActiveFocus()
        })
    }

    Component.onCompleted: filteredModel = options
    onOptionsChanged: filteredModel = userEditing ? filterOptions(field.text) : options
    onVisibleChanged: {
        if (!visible) {
            languagePopup.close()
            finishEditing()
        }
    }

    Button {
        id: displayButton
        objectName: "languageDisplayButton"

        anchors.fill: parent
        visible: !root.userEditing
        enabled: root.enabled
        activeFocusOnTab: true
        leftPadding: 12
        rightPadding: 40
        Accessible.name: I18n.t("Translate to") + ": " + root.labelFor(root.selectedCode)

        contentItem: Text {
            text: root.labelFor(root.selectedCode)
            color: displayButton.enabled ? Theme.text : Theme.textDisabled
            font.pixelSize: Theme.body
            verticalAlignment: Text.AlignVCenter
            textFormat: Text.PlainText
            elide: Text.ElideRight
        }

        background: Rectangle {
            color: displayButton.hovered ? Theme.surfaceMuted : Theme.input
            radius: Theme.radiusSmall
            border.width: displayButton.activeFocus ? 2 : 1
            border.color: displayButton.activeFocus ? Theme.focus : Theme.outline

            Behavior on color {
                ColorAnimation { duration: Theme.motionFast }
            }
        }

        AppIcon {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.icon
            height: Theme.icon
            glyph: "\uE70D"
            iconColor: displayButton.enabled ? Theme.textMuted : Theme.textDisabled
            iconSize: Theme.iconSmall
        }

        Keys.onDownPressed: function(event) {
            root.beginEditing()
            root.focusLanguageList()
            event.accepted = true
        }
        onClicked: root.beginEditing()
    }

    TextField {
        id: field
        objectName: "languageSearchInput"

        anchors.fill: parent
        visible: root.userEditing
        enabled: root.enabled
        placeholderText: root.placeholderText
        selectByMouse: true
        color: root.enabled ? Theme.text : Theme.textDisabled
        placeholderTextColor: Theme.textSubtle
        font.pixelSize: Theme.body
        leftPadding: 12
        rightPadding: 40
        verticalAlignment: TextInput.AlignVCenter
        activeFocusOnTab: true
        Accessible.name: I18n.t("Search language")

        background: Rectangle {
            color: field.hovered ? Theme.surfaceMuted : Theme.input
            radius: Theme.radiusSmall
            border.width: field.activeFocus || languagePopup.opened ? 2 : 1
            border.color: field.activeFocus || languagePopup.opened ? Theme.focus : Theme.outline

            Behavior on color {
                ColorAnimation { duration: Theme.motionFast }
            }
        }

        AppIcon {
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.icon
            height: Theme.icon
            glyph: languagePopup.opened ? "\uE70E" : "\uE70D"
            iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
            iconSize: Theme.iconSmall
        }

        onTextEdited: {
            root.filteredModel = root.filterOptions(text + (inputMethodComposing ? preeditText : ""))
            languageList.currentIndex = root.indexFor(root.selectedCode, root.filteredModel)
            if (!languagePopup.opened)
                languagePopup.open()
        }
        onPreeditTextChanged: root.filteredModel = root.filterOptions(text + preeditText)

        Keys.onDownPressed: function(event) {
            if (!languagePopup.opened)
                languagePopup.open()
            root.focusLanguageList()
            event.accepted = true
        }
        Keys.onReturnPressed: function(event) {
            if (!languagePopup.opened)
                languagePopup.open()
            event.accepted = true
        }
        Keys.onEscapePressed: function(event) {
            languagePopup.close()
            event.accepted = true
        }
    }

    Popup {
        id: languagePopup
        objectName: "languageSearchPopup"

        y: root.height + 6
        width: root.width
        height: Math.min(300, Math.max(54, languageList.contentHeight + 12))
        padding: 6
        modal: false
        focus: false
        z: 100
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        onOpened: languageList.currentIndex = root.indexFor(root.selectedCode, root.filteredModel)
        onClosed: root.finishEditing()

        enter: Transition {
            NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motionFast }
        }
        exit: Transition {
            NumberAnimation { property: "opacity"; from: 1; to: 0; duration: Theme.motionFast }
        }

        background: Rectangle {
            color: Theme.surfaceElevated
            radius: Theme.radius
            border.color: Theme.outlineStrong
            border.width: 1
        }

        ListView {
            id: languageList

            anchors.fill: parent
            clip: true
            model: root.filteredModel
            reuseItems: true
            keyNavigationEnabled: true

            delegate: Item {
                id: row

                required property int index
                required property var modelData

                readonly property bool selectedOption: modelData && modelData.code === root.selectedCode

                width: ListView.view.width
                height: 40
                activeFocusOnTab: false

                Rectangle {
                    anchors.fill: parent
                    radius: Theme.radiusSmall
                    color: row.selectedOption || rowHover.hovered || languageList.currentIndex === row.index
                        ? Theme.interactiveMuted
                        : "transparent"
                }

                Text {
                    anchors.fill: parent
                    anchors.leftMargin: 12
                    anchors.rightMargin: 12
                    text: row.modelData ? row.modelData.label : ""
                    color: row.selectedOption ? Theme.interactive : Theme.text
                    font.pixelSize: Theme.body
                    font.weight: row.selectedOption ? Font.DemiBold : Font.Normal
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                    textFormat: Text.PlainText
                }

                HoverHandler {
                    id: rowHover
                    cursorShape: Qt.PointingHandCursor
                }

                TapHandler {
                    onTapped: {
                        if (row.modelData)
                            root.selected(row.modelData.code)
                        languagePopup.close()
                    }
                }
            }

            Keys.onReturnPressed: function(event) {
                var option = root.filteredModel[currentIndex]
                if (option)
                    root.selected(option.code)
                languagePopup.close()
                event.accepted = true
            }

            ScrollBar.vertical: ScrollBar {
                policy: ScrollBar.AsNeeded
            }
        }
    }
}
