pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "."

Item {
    id: root

    signal requestBack()

    required property var appController
    readonly property var importer: appController.channelImporter
    readonly property bool hasResults: importer.candidateCount > 0
    property string selectedPlatform: "youtube"
    property string syncedSessionId: "\u0000"

    function restoredPlatform() {
        var value = String(importer.requestedPlatform || importer.platform || "").toLowerCase()
        return value === "tiktok" || value === "douyin" ? value : "youtube"
    }

    function platformPlaceholder() {
        if (selectedPlatform === "tiktok")
            return I18n.t("Paste a TikTok profile link")
        if (selectedPlatform === "douyin")
            return I18n.t("Paste a Douyin profile link")
        return I18n.t("Paste a YouTube channel link")
    }

    function contentTypeOptions() {
        if (selectedPlatform === "youtube") {
            return [
                { "label": I18n.t("All YouTube videos"), "value": "all" },
                { "label": I18n.t("YouTube Shorts"), "value": "short" },
                { "label": I18n.t("Regular YouTube videos"), "value": "long" }
            ]
        }
        return [
            { "label": I18n.t("Video posts"), "value": "all" }
        ]
    }

    function syncAuthentication() {
        if (importer.cookieFile.length > 0)
            authentication.currentIndex = 3
        else if (importer.cookieBrowser === "edge")
            authentication.currentIndex = 1
        else if (importer.cookieBrowser === "chrome")
            authentication.currentIndex = 2
        else
            authentication.currentIndex = 0
    }

    function syncSessionDraft() {
        const sessionId = String(importer.sessionId || "")
        if (syncedSessionId === sessionId) {
            syncAuthentication()
            return
        }

        syncedSessionId = sessionId
        const request = importer.requestData || ({})
        selectedPlatform = restoredPlatform()
        channelUrl.text = String(request.url || importer.channelUrl || "")
        ranking.currentIndex = request.ranking === "popular" ? 1 : 0
        importLimit.value = Math.max(importLimit.from, Math.min(importLimit.to, Number(request.limit || 20)))
        if (selectedPlatform === "youtube") {
            const durationFilter = String(request.duration_filter || "short")
            contentFilter.currentIndex = durationFilter === "all" ? 0 : durationFilter === "long" ? 2 : 1
        } else {
            contentFilter.currentIndex = 0
        }
        const scanScopeValue = Number(request.scan_scope || 300)
        scanScope.currentIndex = scanScopeValue === 100 ? 0
            : scanScopeValue === 1000 ? 2
            : scanScopeValue === 0 ? 3
            : 1
        syncAuthentication()
    }

    Component.onCompleted: {
        root.appController.prepareChannelImport()
        syncSessionDraft()
    }

    Connections {
        target: root.importer

        function onChanged() {
            root.syncSessionDraft()
        }
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: Theme.space16

        PageHeader {
            Layout.fillWidth: true
            title: I18n.t("Import from channel")
            subtitle: root.appController.projectName

            AppButton {
                text: I18n.t("Back")
                iconGlyph: "\uE72B"
                tone: "secondary"
                onClicked: root.requestBack()
            }

            AppButton {
                visible: root.importer.busy
                text: I18n.t("Cancel import")
                iconGlyph: "\uE711"
                tone: "danger"
                onClicked: root.importer.cancel()
            }
        }

        Panel {
            Layout.fillWidth: true
            title: I18n.t("Channel source")
            subtitle: I18n.t("Choose a platform, then paste its channel or profile link")

            ColumnLayout {
                Layout.fillWidth: true
                spacing: Theme.space4

                Text {
                    text: I18n.t("Platform")
                    color: Theme.textMuted
                    font.pixelSize: Theme.label
                    textFormat: Text.PlainText
                }

                SegmentedControl {
                    Layout.fillWidth: true
                    options: [
                        { "label": "YouTube", "value": "youtube" },
                        { "label": "TikTok", "value": "tiktok" },
                        { "label": I18n.t("Douyin Beta"), "value": "douyin" }
                    ]
                    currentValue: root.selectedPlatform
                    enabled: !root.importer.busy
                    onActivated: function(value) {
                        root.selectedPlatform = value
                        contentFilter.currentIndex = value === "youtube" ? 1 : 0
                        channelUrl.forceActiveFocus()
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: Theme.space12

                TextField {
                    id: channelUrl

                    Layout.fillWidth: true
                    implicitHeight: 44
                    placeholderText: root.platformPlaceholder()
                    color: Theme.text
                    font.pixelSize: Theme.body
                    selectByMouse: true
                    activeFocusOnTab: true
                    enabled: !root.importer.busy
                    Accessible.name: I18n.t("Channel link")
                    background: Rectangle {
                        radius: Theme.radiusSmall
                        color: Theme.input
                        border.width: channelUrl.activeFocus ? 2 : 1
                        border.color: channelUrl.activeFocus ? Theme.focus : Theme.outline
                    }
                    Keys.onReturnPressed: {
                        if (inspectButton.enabled)
                            inspectButton.clicked()
                    }
                }

                AppButton {
                    id: inspectButton

                    text: root.hasResults ? I18n.t("Scan again") : I18n.t("Preview videos")
                    iconGlyph: "\uE721"
                    tone: "primary"
                    enabled: channelUrl.text.trim().length > 0 && !root.importer.busy
                    onClicked: root.importer.inspect(
                        channelUrl.text.trim(),
                        root.selectedPlatform,
                        ranking.currentValue,
                        importLimit.value,
                        contentFilter.currentValue,
                        ranking.currentValue === "popular" ? scanScope.currentValue : 0
                    )
                }
            }

            GridLayout {
                Layout.fillWidth: true
                // At the minimum desktop width this still fits five compact controls;
                // keeping it to one row leaves room for a full candidate card at 720 px.
                columns: width >= 900 ? 5 : 3
                columnSpacing: Theme.space12
                rowSpacing: Theme.space12

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Order")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    AppComboBox {
                        id: ranking
                        Layout.fillWidth: true
                        model: [
                            { "label": I18n.t("Newest"), "value": "newest" },
                            { "label": I18n.t("Most viewed"), "value": "popular" }
                        ]
                        textRole: "label"
                        valueRole: "value"
                        enabled: !root.importer.busy
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Import limit")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    AppSpinBox {
                        id: importLimit
                        Layout.fillWidth: true
                        from: 1
                        to: 100
                        value: 20
                        enabled: !root.importer.busy
                        Accessible.name: I18n.t("Import limit")
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Content type")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    AppComboBox {
                        id: contentFilter
                        Layout.fillWidth: true
                        model: root.contentTypeOptions()
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: 1
                        enabled: !root.importer.busy
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    visible: ranking.currentValue === "popular"
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Scan range")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    AppComboBox {
                        id: scanScope
                        Layout.fillWidth: true
                        model: [
                            { "label": I18n.t("100 videos"), "value": 100 },
                            { "label": I18n.t("300 videos"), "value": 300 },
                            { "label": I18n.t("1000 videos"), "value": 1000 },
                            { "label": I18n.t("All available"), "value": 0 }
                        ]
                        textRole: "label"
                        valueRole: "value"
                        currentIndex: 1
                        enabled: !root.importer.busy
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space4

                    Text {
                        text: I18n.t("Access")
                        color: Theme.textMuted
                        font.pixelSize: Theme.label
                        textFormat: Text.PlainText
                    }

                    AppComboBox {
                        id: authentication
                        Layout.fillWidth: true
                        model: [
                            I18n.t("Public videos"),
                            I18n.t("Use Edge session"),
                            I18n.t("Use Chrome session"),
                            I18n.t("Choose cookies.txt")
                        ]
                        enabled: !root.importer.busy
                        onActivated: function(index) {
                            if (index === 1)
                                root.importer.setCookieBrowser("edge")
                            else if (index === 2)
                                root.importer.setCookieBrowser("chrome")
                            else if (index === 3)
                                root.importer.browseCookieFile()
                            else
                                root.importer.clearAuthentication()
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                visible: root.importer.status.length > 0
                spacing: Theme.space8

                AppIcon {
                    Layout.preferredWidth: 18
                    Layout.preferredHeight: 18
                    glyph: root.importer.state === "error" ? "\uEA39" : "\uE946"
                    iconColor: root.importer.state === "error" ? Theme.danger : Theme.textMuted
                    iconSize: Theme.iconSmall
                }

                Text {
                    Layout.fillWidth: true
                    text: I18n.channelImportStatus(root.importer.status)
                    color: root.importer.state === "error" ? Theme.danger : Theme.textMuted
                    font.pixelSize: Theme.caption
                    textFormat: Text.PlainText
                    wrapMode: Text.WordWrap
                }

                Text {
                    visible: root.importer.platform === "Douyin"
                    text: I18n.t("Beta")
                    color: Theme.warning
                    font.pixelSize: Theme.label
                    font.weight: Font.DemiBold
                    textFormat: Text.PlainText
                }
            }

            AppProgressBar {
                Layout.fillWidth: true
                visible: root.importer.busy
                value: root.importer.progress
            }
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.fillHeight: true
            radius: Theme.radius
            color: Theme.surface
            border.width: 1
            border.color: Theme.outline

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: Theme.space16
                spacing: Theme.space12

                RowLayout {
                    Layout.fillWidth: true
                    spacing: Theme.space12

                    Text {
                        Layout.fillWidth: true
                        text: root.importer.channelName.length > 0
                            ? root.importer.channelName
                            : I18n.t("Channel videos")
                        color: Theme.text
                        font.pixelSize: Theme.h2
                        font.weight: Font.DemiBold
                        textFormat: Text.PlainText
                        elide: Text.ElideRight
                    }

                    Text {
                        visible: root.hasResults
                        text: qsTr("%1 %2").arg(root.importer.candidateCount).arg(I18n.t("videos"))
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        textFormat: Text.PlainText
                    }

                    AppCheckBox {
                        visible: root.hasResults
                        text: I18n.t("Select all")
                        checked: root.importer.selectedCount > 0
                            && root.importer.selectedCount === root.importer.selectableCount
                        enabled: !root.importer.busy
                        onToggled: root.importer.selectAll(checked)
                    }

                    AppButton {
                        visible: root.hasResults
                        text: qsTr("%1 (%2)").arg(I18n.t("Download selected")).arg(root.importer.selectedCount)
                        iconGlyph: "\uE896"
                        tone: "primary"
                        enabled: root.importer.selectedCount > 0 && !root.importer.busy
                        onClicked: root.appController.startChannelDownloads()
                    }
                }

                Rectangle {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 1
                    color: Theme.divider
                }

                ListView {
                    id: candidateList

                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    Layout.minimumHeight: 92
                    clip: true
                    model: root.importer.candidateModel
                    reuseItems: true
                    boundsBehavior: Flickable.StopAtBounds
                    spacing: 0

                    delegate: ChannelVideoRow {
                        width: candidateList.width
                        onSelectionChanged: function(selected) {
                            root.importer.setSelected(index, selected)
                        }
                        onRetryRequested: root.appController.retryChannelVideo(index)
                    }

                    ScrollBar.vertical: ScrollBar {
                        policy: ScrollBar.AsNeeded
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    visible: !root.hasResults && !root.importer.busy
                    spacing: Theme.space8

                    Item { Layout.fillHeight: true }

                    AppIcon {
                        Layout.alignment: Qt.AlignHCenter
                        Layout.preferredWidth: 38
                        Layout.preferredHeight: 38
                        glyph: "\uE71B"
                        iconColor: Theme.textSubtle
                        iconSize: 30
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Preview a channel to choose videos")
                        color: Theme.text
                        font.pixelSize: Theme.h3
                        font.weight: Font.DemiBold
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                    }

                    Text {
                        Layout.fillWidth: true
                        text: I18n.t("Downloaded videos are added to this batch without starting processing")
                        color: Theme.textMuted
                        font.pixelSize: Theme.caption
                        horizontalAlignment: Text.AlignHCenter
                        textFormat: Text.PlainText
                        wrapMode: Text.WordWrap
                    }

                    Item { Layout.fillHeight: true }
                }
            }
        }
    }
}
