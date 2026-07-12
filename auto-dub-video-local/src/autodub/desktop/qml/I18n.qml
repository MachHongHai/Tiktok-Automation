pragma Singleton
import QtQuick

QtObject {
    property string language: "en"

    function t(source) {
        if (language !== "vi")
            return source
        const vi = {
            "Create": "Tạo mới",
            "Projects": "Projects",
            "Workspace": "Không gian xử lý",
            "Batch": "Hàng đợi",
            "Job Detail": "Chi tiết công việc",
            "WORKSPACE": "KHÔNG GIAN LÀM VIỆC",
            "Settings": "Cài đặt",
            "Appearance": "Giao diện",
            "Theme": "Chủ đề",
            "Dark": "Tối",
            "Light": "Sáng",
            "Language": "Ngôn ngữ",
            "English": "Tiếng Anh",
            "Vietnamese": "Tiếng Việt",
            "Browse": "Chọn thư mục",
            "Apply settings": "Áp dụng cài đặt",
            "Reset defaults": "Khôi phục mặc định",
            "Create a new dub": "Tạo video lồng tiếng mới",
            "Turn one source video into a translated, voiced and captioned export.": "Chuyển video nguồn thành bản dịch, lồng tiếng và phụ đề.",
            "Source media": "Video nguồn",
            "Input video and subtitle placement": "Video đầu vào và vị trí phụ đề",
            "Dubbing setup": "Thiết lập lồng tiếng",
            "Language, voice and output behavior": "Ngôn ngữ, giọng đọc và định dạng xuất",
            "Activity log": "Nhật ký hoạt động",
            "Live processing output": "Tiến trình xử lý trực tiếp",
            "Select a source video": "Chọn video nguồn",
            "Drop video to import": "Thả video để nhập",
            "Release to add the source file": "Thả để thêm video nguồn",
            "Source imported": "Đã nhập video nguồn",
            "No source selected": "Chưa chọn video nguồn",
            "Choose a file to begin": "Chọn một tệp để bắt đầu",
            "Replace": "Thay thế",
            "Edit subtitle frame": "Chỉnh khung phụ đề",
            "Full Auto workflow": "Quy trình tự động",
            "Source": "Nguồn",
            "Translate to": "Dịch sang",
            "Voice": "Giọng đọc",
            "Layout": "Bố cục",
            "Separate vocals for music or noisy audio": "Tách giọng nói khi có nhạc hoặc tạp âm",
            "Match voices to detected speakers": "Tự ghép giọng theo người nói",
            "Original audio": "Âm thanh gốc",
            "Create and process": "Tạo và xử lý",
            "Open output": "Mở video xuất",
            "Stop": "Dừng",
            "No active job": "Không có job đang chạy",
            "Last export ready": "Bản xuất gần nhất đã sẵn sàng",
            "Processing status will appear here": "Trạng thái xử lý sẽ hiển thị tại đây",
            "Appearance, language and output location": "Giao diện, ngôn ngữ và nơi xuất video",
            "Appearance and language": "Giao diện và ngôn ngữ",
            "Apply changes instantly across the desktop app": "Áp dụng thay đổi ngay trong ứng dụng",
            "Create project": "Tạo project",
            "Name this project and choose where its final video will be saved.": "Đặt tên project và chọn nơi lưu video hoàn tất.",
            "Project name": "Tên project",
            "Project folder": "Thư mục project",
            "Example: Summer campaign": "Ví dụ: Chiến dịch mùa hè",
            "The final video will be saved inside a folder named after this project.": "Video hoàn tất sẽ được lưu trong thư mục mang tên project.",
            "Cancel": "Hủy"
            ,"Close": "Đóng"
            ,"Continue": "Tiếp tục"
            ,"Create a project or reopen previous work.": "Tạo project mới hoặc mở lại công việc trước đây."
            ,"New project": "Project mới"
            ,"Recent projects": "Project gần đây"
            ,"Select a project to inspect its job and output.": "Chọn project để xem job và video xuất."
            ,"No preview": "Chưa có preview"
            ,"Batch queue": "Hàng đợi xử lý"
            ,"Process a video collection with one shared dubbing setup.": "Xử lý nhiều video với một thiết lập lồng tiếng chung."
            ,"Clear": "Xóa danh sách"
            ,"Add videos": "Thêm video"
            ,"Running queue": "Đang chạy hàng đợi"
            ,"Start queue": "Bắt đầu hàng đợi"
            ,"Videos": "Video"
            ,"Completed": "Hoàn tất"
            ,"Target": "Ngôn ngữ đích"
            ,"Queue processing": "Đang xử lý hàng đợi"
            ,"Overall progress": "Tiến độ tổng"
            ,"Video jobs": "Các video trong hàng đợi"
            ,"Add videos to build a batch": "Thêm video để tạo hàng đợi"
            ,"Drop MP4, MOV or MKV files here": "Thả tệp MP4, MOV hoặc MKV tại đây"
            ,"Job library": "Thư viện job"
            ,"Review every run, inspect progress and reopen finished exports.": "Xem lại các lần chạy, theo dõi tiến độ và mở video đã hoàn tất."
            ,"Refresh": "Làm mới"
            ,"Recent jobs": "Job gần đây"
            ,"Newest activity appears first": "Hoạt động mới nhất hiển thị trước"
            ,"Back": "Quay lại"
            ,"Run status": "Trạng thái chạy"
            ,"Live pipeline progress": "Tiến độ pipeline trực tiếp"
            ,"Status": "Trạng thái"
            ,"Output": "Đầu ra"
            ,"Elapsed": "Đã chạy"
            ,"Time running": "Thời gian đã chạy"
            ,"Processing time": "Tổng thời gian xử lý"
            ,"Estimated remaining": "Còn ước tính"
            ,"Actions": "Thao tác"
            ,"Open input video": "Mở video nguồn"
            ,"Open output video": "Mở video xuất"
            ,"Open output folder": "Mở thư mục xuất"
            ,"Open job folder": "Mở thư mục job"
            ,"Delete job": "Xóa job"
            ,"Processing output for this job": "Tiến trình xử lý của job này"
        }
        return vi[source] || source
    }
}
