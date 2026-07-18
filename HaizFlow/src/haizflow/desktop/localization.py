"""Localized wrappers for native Qt dialogs.

QML owns visible application copy; this module keeps native file and message
dialogs aligned with the persisted UI language.
"""

import re

from PySide6.QtWidgets import QFileDialog as QtFileDialog, QMessageBox as QtMessageBox

_UI_LANGUAGE = "en"


def _set_ui_language(language: str) -> None:
    global _UI_LANGUAGE
    _UI_LANGUAGE = "vi" if language == "vi" else "en"


def _ui_text(value) -> str:
    text = str(value)
    if _UI_LANGUAGE != "vi":
        return text

    translations = {
        "Replace video": "Thay video",
        "Invalid video": "Video không hợp lệ",
        "Unsupported file": "Tệp không được hỗ trợ",
        "Project name": "Tên dự án",
        "Project storage location": "Vị trí lưu dự án",
        "Processing device": "Thiết bị xử lý",
        "Settings": "Cài đặt",
        "Import video": "Nhập video",
        "Channel import": "Nhập video từ kênh",
        "Some videos were skipped": "Một số video đã bị bỏ qua",
        "Batch delete incomplete": "Chưa xóa hết dự án hàng loạt",
        "No supported videos": "Không có video được hỗ trợ",
        "Batch queue": "Hàng đợi xử lý",
        "Batch settings": "Thiết lập hàng loạt",
        "Stop batch": "Dừng hàng đợi",
        "Missing video": "Thiếu video",
        "Cannot start project": "Không thể bắt đầu dự án",
        "Cannot create project": "Không thể tạo dự án",
        "Pause video": "Tạm dừng video",
        "Restart video": "Chạy lại video",
        "Translation review": "Duyệt bản dịch",
        "No video selected": "Chưa chọn video",
        "Remove video": "Xóa video",
        "Delete failed": "Xóa không thành công",
        "Already removed": "Đã xóa",
        "Project folder": "Thư mục dự án",
        "Delete project": "Xóa dự án",
        "Input preview": "Xem trước đầu vào",
        "Subtitle presets": "Khung phụ đề",
        "GPU mode requires AC power for stable processing. Connect the charger and try again.": "Chế độ GPU cần cắm sạc để xử lý ổn định. Hãy cắm sạc rồi thử lại.",
        "Open input video": "Mở video nguồn",
        "Open output": "Mở video đầu ra",
        "Open export folder": "Mở thư mục video xuất",
        "Choose input video": "Chọn video nguồn",
        "Choose project storage location": "Chọn vị trí lưu dự án",
        "Choose videos for batch processing": "Chọn video để xử lý hàng loạt",
        "Choose a folder of videos for batch processing": "Chọn thư mục video để xử lý hàng loạt",
        "Choose cookies.txt": "Chọn cookies.txt",
        "Video files (*.mp4 *.mov *.mkv);;All files (*.*)": "Tệp video (*.mp4 *.mov *.mkv);;Tất cả tệp (*.*)",
        "Netscape cookie files (*.txt);;All files (*.*)": "Tệp cookie Netscape (*.txt);;Tất cả tệp (*.*)",
        "Pause or finish this video before replacing it.": "Hãy tạm dừng hoặc hoàn tất video này trước khi thay thế.",
        "Choose an MP4, MOV, or MKV video file.": "Hãy chọn tệp video MP4, MOV hoặc MKV.",
        "Enter a project name.": "Hãy nhập tên dự án.",
        "Choose a location for this project.": "Hãy chọn vị trí lưu dự án này.",
        "Wait for the current processing task to finish before changing device.": "Hãy chờ tác vụ hiện tại hoàn tất trước khi đổi thiết bị xử lý.",
        "Wait for the current processing task to finish before resetting the device setting.": "Hãy chờ tác vụ hiện tại hoàn tất trước khi khôi phục thiết bị xử lý mặc định.",
        "Wait for the processing device to finish switching before restarting.": "Hãy chờ thiết bị xử lý chuyển xong trước khi chạy lại.",
        "The dropped file is unavailable.": "Tệp được kéo thả không khả dụng.",
        "Choose MP4, MOV, or MKV video files.": "Hãy chọn các tệp video MP4, MOV hoặc MKV.",
        "Add at least one video to the queue.": "Hãy thêm ít nhất một video vào hàng đợi.",
        "These videos are already waiting or processing.": "Các video này đã có trong hàng đợi hoặc đang được xử lý.",
        "Add at least one video before applying settings.": "Hãy thêm ít nhất một video trước khi áp dụng thiết lập.",
        "Stop the active video and cancel the remaining queue?": "Dừng video đang chạy và hủy các video còn lại trong hàng đợi?",
        "Please choose an input video.": "Hãy chọn video nguồn.",
        "Pause this video? You can resume it later from Projects.": "Tạm dừng video này? Bạn có thể tiếp tục lại từ Dự án.",
        "Apply the current dubbing setup and restart this project?": "Áp dụng thiết lập lồng tiếng hiện tại và chạy lại dự án này?",
        "Select a video in this batch first.": "Hãy chọn một video trong dự án hàng loạt trước.",
        "Video data was already removed.": "Dữ liệu video đã được xóa.",
        "This project's folder is not available yet.": "Thư mục của dự án này chưa khả dụng.",
        "Select a project first.": "Hãy chọn một dự án trước.",
        "Choose an input video before opening the preview editor.": "Hãy chọn video nguồn trước khi mở trình chỉnh khung phụ đề.",
        "Add at least one video before editing subtitles.": "Hãy thêm ít nhất một video trước khi chỉnh phụ đề.",
        "Input video is not available yet.": "Video nguồn chưa khả dụng.",
        "Final video is not available yet.": "Video đầu ra chưa khả dụng.",
        "The export folder is not available yet.": "Thư mục video xuất chưa khả dụng.",
        "The destination project no longer exists.": "Dự án đích không còn tồn tại.",
        "Open or create a batch project before importing a channel.": "Hãy mở hoặc tạo một dự án hàng loạt trước khi nhập video từ kênh.",
        "Channel import is still stopping. Try deleting the project again in a moment.": "Tiến trình nhập từ kênh vẫn đang dừng. Hãy thử xóa lại dự án sau giây lát.",
    }
    if text in translations:
        return translations[text]

    replacements = (
        ("Cannot create the project at this location: ", "Không thể tạo dự án tại vị trí này: "),
        ("Cannot save settings: ", "Không thể lưu cài đặt: "),
        ("Cannot restore defaults: ", "Không thể khôi phục cài đặt mặc định: "),
        ("GPU mode requires at least ", "Chế độ GPU cần ít nhất "),
        ("CPU mode requires approximately ", "Chế độ CPU cần khoảng "),
        ("CUDA-compatible NVIDIA GPU was not detected.", "Không phát hiện GPU NVIDIA tương thích CUDA."),
        ("Automatic mode will use the CPU because a compatible GPU is unavailable.", "Chế độ tự động sẽ dùng CPU vì không có GPU tương thích."),
        ("This computer does not meet the minimum CPU or GPU memory requirement.", "Máy không đáp ứng yêu cầu bộ nhớ tối thiểu của CPU hoặc GPU."),
    )
    for source, translated in replacements:
        if text.startswith(source):
            return translated + text[len(source):]
        if text == source:
            return translated

    skipped = re.match(r"^(\d+) unsupported or unreadable item\(s\):(.*)$", text, re.DOTALL)
    if skipped:
        return f"{skipped.group(1)} mục không được hỗ trợ hoặc không thể đọc:{skipped.group(2)}"
    return text


class QMessageBox(QtMessageBox):
    """Keep native dialogs aligned with the application language setting."""

    @staticmethod
    def information(parent, title, text, *args):
        return QtMessageBox.information(parent, _ui_text(title), _ui_text(text), *args)

    @staticmethod
    def warning(parent, title, text, *args):
        return QtMessageBox.warning(parent, _ui_text(title), _ui_text(text), *args)

    @staticmethod
    def critical(parent, title, text, *args):
        return QtMessageBox.critical(parent, _ui_text(title), _ui_text(text), *args)

    @staticmethod
    def question(parent, title, text, *args):
        return QtMessageBox.question(parent, _ui_text(title), _ui_text(text), *args)


class QFileDialog(QtFileDialog):
    """Use localized captions for native file dialogs while retaining Qt's API."""

    @staticmethod
    def getOpenFileName(parent=None, caption="", directory="", filter="", *args):
        return QtFileDialog.getOpenFileName(parent, _ui_text(caption), directory, _ui_text(filter), *args)

    @staticmethod
    def getOpenFileNames(parent=None, caption="", directory="", filter="", *args):
        return QtFileDialog.getOpenFileNames(parent, _ui_text(caption), directory, _ui_text(filter), *args)

    @staticmethod
    def getExistingDirectory(parent=None, caption="", directory="", options=QtFileDialog.Option.ShowDirsOnly):
        return QtFileDialog.getExistingDirectory(parent, _ui_text(caption), directory, options)
