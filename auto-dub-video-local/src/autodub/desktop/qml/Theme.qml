pragma Singleton
import QtQuick

QtObject {
    property bool darkMode: true
    property bool motionEnabled: true

    readonly property color window: darkMode ? "#0f1216" : "#f4f6f8"
    readonly property color surface: darkMode ? "#171b21" : "#ffffff"
    readonly property color surfaceElevated: darkMode ? "#1d2229" : "#f8fafb"
    readonly property color surfaceMuted: darkMode ? "#242a32" : "#edf1f4"
    readonly property color surfaceStrong: darkMode ? "#2d3540" : "#dfe5ea"
    readonly property color input: darkMode ? "#151a20" : "#ffffff"
    readonly property color sidebar: darkMode ? "#0a0d11" : "#e9eef2"
    readonly property color sidebarHover: darkMode ? "#14191f" : "#dde5eb"
    readonly property color sidebarSelected: darkMode ? "#182126" : "#ffffff"
    readonly property color topBar: darkMode ? "#11151a" : "#f9fafb"
    readonly property color outline: darkMode ? "#2d3540" : "#cbd4dc"
    readonly property color outlineStrong: darkMode ? "#465160" : "#9eacb8"
    readonly property color divider: darkMode ? "#252c35" : "#dce3e8"

    readonly property color text: darkMode ? "#f3f5f7" : "#17212b"
    readonly property color textMuted: darkMode ? "#a9b2be" : "#526273"
    readonly property color textSubtle: darkMode ? "#737e8d" : "#748596"
    readonly property color textDisabled: darkMode ? "#586270" : "#93a1ae"
    readonly property color textOnAccent: darkMode ? "#07110f" : "#ffffff"
    readonly property color textOnDark: darkMode ? "#f5f7f9" : "#17212b"
    readonly property color textOnDarkMuted: darkMode ? "#a0aab7" : "#526273"

    readonly property color interactive: darkMode ? "#5acbbd" : "#087f73"
    readonly property color interactiveHover: darkMode ? "#70d9cc" : "#096f66"
    readonly property color interactivePressed: darkMode ? "#40ad9f" : "#065f57"
    readonly property color interactiveMuted: darkMode ? "#173a37" : "#d9f0ed"
    readonly property color focus: darkMode ? "#7de1d5" : "#0a8f81"

    readonly property color blue: darkMode ? "#7eaeff" : "#2567d5"
    readonly property color blueMuted: darkMode ? "#1a2f4c" : "#e0ebff"
    readonly property color danger: darkMode ? "#ff8275" : "#c93c32"
    readonly property color dangerMuted: darkMode ? "#47241f" : "#fbe5e2"
    readonly property color success: darkMode ? "#58d7a2" : "#16865c"
    readonly property color successMuted: darkMode ? "#17382d" : "#dcf3e9"
    readonly property color warning: darkMode ? "#f0c56b" : "#9a6500"
    readonly property color warningMuted: darkMode ? "#43371e" : "#f7ecd2"
    readonly property color scrim: darkMode ? "#b3000000" : "#660d1720"
    readonly property color video: "#050607"
    readonly property color codeSurface: darkMode ? "#0b0e12" : "#f7f9fb"
    readonly property color codeText: darkMode ? "#cbd5df" : "#344353"
    readonly property color captionOverlay: darkMode ? "#d911151a" : "#d917212b"
    readonly property color captionText: "#ffffff"

    readonly property int radius: 8
    readonly property int radiusSmall: 6
    readonly property int radiusTiny: 4

    readonly property int space4: 4
    readonly property int space8: 8
    readonly property int space12: 12
    readonly property int space16: 16
    readonly property int space20: 20
    readonly property int space24: 24
    readonly property int space32: 32
    readonly property int gap: space16

    readonly property int label: 12
    readonly property int caption: 13
    readonly property int body: 15
    readonly property int bodyLarge: 16
    readonly property int h3: 18
    readonly property int h2: 21
    readonly property int h1: 28
    readonly property int display: 34

    readonly property int iconSmall: 15
    readonly property int icon: 18
    readonly property int iconLarge: 22
    readonly property string iconFont: "Segoe Fluent Icons"

    readonly property int motionFast: motionEnabled ? 100 : 0
    readonly property int motionStandard: motionEnabled ? 180 : 0
    readonly property int motionSlow: motionEnabled ? 260 : 0
    readonly property int navigationExpanded: 236
    readonly property int navigationCompact: 84
    readonly property int commandBarHeight: 62
}
