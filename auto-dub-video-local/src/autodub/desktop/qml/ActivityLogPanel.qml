import QtQuick
import QtQuick.Layouts
import "."

Panel {
    id: root

    title: I18n.t("Activity log")
    subtitle: controller.hasSelectedJob
        ? controller.selectedFileName + "  ·  " + I18n.t(controller.selectedStatus)
        : I18n.t("Live processing output")
    contentPadding: 18

    LogViewer {
        Layout.fillWidth: true
        Layout.fillHeight: true
        text: controller.logs
        emptyText: I18n.t("Logs will appear here while a job is processing.")
    }
}
