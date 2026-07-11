pragma Singleton
import QtQuick

QtObject {
    property bool darkMode: true
    readonly property color window: darkMode ? "#121417" : "#f5f7fa"
    readonly property color surface: darkMode ? "#1b1e23" : "#ffffff"
    readonly property color surfaceElevated: darkMode ? "#22262c" : "#f8fafc"
    readonly property color surfaceMuted: darkMode ? "#2a2f36" : "#e9eef3"
    readonly property color surfaceStrong: darkMode ? "#313740" : "#dce4eb"
    readonly property color sidebar: darkMode ? "#0d0f12" : "#eef2f5"
    readonly property color sidebarMuted: darkMode ? "#181b20" : "#e1e8ed"
    readonly property color outline: darkMode ? "#343a43" : "#cbd5df"
    readonly property color outlineStrong: darkMode ? "#4b5563" : "#9dacba"
    readonly property color text: darkMode ? "#f4f6f8" : "#17212b"
    readonly property color textMuted: darkMode ? "#a3abb8" : "#526273"
    readonly property color textSubtle: darkMode ? "#707987" : "#78899a"
    readonly property color textOnDark: darkMode ? "#f7fafc" : "#17212b"
    readonly property color textOnDarkMuted: darkMode ? "#949daa" : "#526273"
    readonly property color interactive: darkMode ? "#55c7b7" : "#087f73"
    readonly property color interactiveHover: darkMode ? "#6edbcb" : "#0b9788"
    readonly property color interactiveMuted: darkMode ? "#173c39" : "#d7f1ed"
    readonly property color blue: "#74a9ff"
    readonly property color blueMuted: "#1c304f"
    readonly property color danger: "#ff7a6b"
    readonly property color dangerMuted: "#47231f"
    readonly property color success: "#55d6a0"
    readonly property color successMuted: "#173a2d"
    readonly property color warning: "#f2c66d"
    readonly property color warningMuted: "#45391e"

    readonly property int radius: 8
    readonly property int radiusSmall: 6
    readonly property int gap: 16
    readonly property int body: 16
    readonly property int caption: 13
    readonly property int h2: 20
    readonly property int h1: 28
    readonly property int display: 36
}
