import unittest

from haizflow.desktop.qml_controller import _set_ui_language, _ui_text


class UiLocalizationTests(unittest.TestCase):
    def tearDown(self):
        _set_ui_language("en")

    def test_native_dialog_text_uses_vietnamese_when_selected(self):
        _set_ui_language("vi")

        self.assertEqual(_ui_text("Replace video"), "Thay video")
        self.assertEqual(
            _ui_text("Choose an MP4, MOV, or MKV video file."),
            "Hãy chọn tệp video MP4, MOV hoặc MKV.",
        )

    def test_native_dialog_text_uses_english_when_selected(self):
        _set_ui_language("en")

        self.assertEqual(_ui_text("Replace video"), "Replace video")

    def test_dynamic_native_dialog_prefix_is_localized(self):
        _set_ui_language("vi")

        self.assertEqual(
            _ui_text("Cannot save settings: permission denied"),
            "Không thể lưu cài đặt: permission denied",
        )


if __name__ == "__main__":
    unittest.main()
