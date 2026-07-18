import QtQuick
import QtQuick.Layouts
import "."

Panel {
    id: root

    title: I18n.t("Activity log")
    subtitle: AppController.hasSelectedVideo
        ? AppController.selectedFileName + "  ·  " + I18n.t(AppController.selectedStatus)
        : I18n.t("Live processing output")
    contentPadding: 18

    LogViewer {
        Layout.fillWidth: true
        Layout.fillHeight: true
        text: AppController.logs
        emptyText: I18n.t("Logs will appear here while this project is processing.")
    }
}
