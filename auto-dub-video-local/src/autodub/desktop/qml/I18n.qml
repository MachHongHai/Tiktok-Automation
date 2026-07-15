pragma Singleton
import QtQuick

QtObject {
    property string language: "en"

    function stageLabel(stage) {
        const labels = {
            "queued": "Queued",
            "starting": "Preparing project",
            "loading_models": "Preparing translation model",
            "loading_alignment": "Preparing subtitle alignment",
            "extracting_audio": "Extracting audio",
            "separating_audio": "Separating vocals",
            "transcribing": "Transcribing speech",
            "translating": "Translating",
            "review_translation": "Waiting for translation review",
            "creating_subtitle": "Creating subtitles",
            "creating_voice": "Generating voice",
            "building_audio_timeline": "Mixing audio",
            "rendering": "Rendering video",
            "paused": "Paused",
            "done": "Export complete",
            "failed": "Failed"
        }
        return t(labels[stage] || stage)
    }

    function taskStateLabel(state) {
        const labels = {
            "active": "In progress",
            "pending": "Queued",
            "done": "Complete",
            "failed": "Failed",
            "cancelled": "Cancelled"
        }
        return t(labels[state] || state)
    }

    function runtimeStatus(source) {
        if (language !== "vi" || !source)
            return source

        const direct = t(source)
        if (direct !== source)
            return direct

        if (source.indexOf("_") >= 0)
            return stageLabel(source)

        let match = source.match(/^(.+?) ready - GPU acceleration - (.+)$/)
        if (match)
            return match[1] + " đã sẵn sàng - Tăng tốc GPU: " + match[2]

        match = source.match(/^(.+?) ready - CPU mode - (.+)$/)
        if (match)
            return match[1] + " đã sẵn sàng - Chế độ CPU: " + match[2].replace(/threads$/, "luồng")

        match = source.match(/^Ready - GPU acceleration - (.+)$/)
        if (match)
            return "Sẵn sàng - Tăng tốc GPU: " + match[1]

        match = source.match(/^Ready - CPU mode - (.+)$/)
        if (match)
            return "Sẵn sàng - Chế độ CPU: " + match[1].replace(/threads$/, "luồng")

        match = source.match(/^Model warm-up unavailable: (.+)$/)
        if (match)
            return "Không thể khởi tạo model: " + match[1]

        match = source.match(/^Processing device switch failed: (.+)$/)
        if (match)
            return "Không thể chuyển thiết bị xử lý: " + match[1]

        match = source.match(/^Saved processing device unavailable: (.+) Using automatic mode\.$/)
        if (match)
            return "Thiết bị xử lý đã lưu không khả dụng: " + match[1] + " Đã chuyển sang chế độ tự động."

        match = source.match(/^Organized (\d+) video workspace\(s\) into their projects\.$/)
        if (match)
            return "Đã sắp xếp " + match[1] + " video vào dự án tương ứng."

        return source
    }

    function progressDetail(source) {
        if (language !== "vi" || !source)
            return source

        const direct = t(source)
        if (direct !== source)
            return direct

        let match = source.match(/^Translating subtitles (\d+)-(\d+) of (\d+)$/)
        if (match)
            return "Đang dịch phụ đề " + match[1] + "-" + match[2] + " / " + match[3]

        match = source.match(/^Translated (\d+) of (\d+) subtitles$/)
        if (match)
            return "Đã dịch " + match[1] + " / " + match[2] + " phụ đề"

        match = source.match(/^Paused during (.+)$/)
        if (match)
            return "Đã tạm dừng tại bước: " + stageLabel(match[1])

        match = source.match(/^Queued: position (\d+)$/)
        if (match)
            return "Đang chờ ở vị trí " + match[1]

        match = source.match(/^Loading HY-MT2 Q4 CPU model with (\d+) threads$/)
        if (match)
            return "Đang tải model HY-MT2 Q4 cho CPU với " + match[1] + " luồng"

        match = source.match(/^HY-MT2 weights loaded; moving model to (.+)$/)
        if (match)
            return "Đã tải trọng số HY-MT2; đang chuyển model sang " + match[1]

        return source
    }

    function t(source) {
        if (language !== "vi")
            return source

        const vi = {
            "Workspace": "Không gian làm việc",
            "WORKSPACE": "KHÔNG GIAN LÀM VIỆC",
            "Video Dubbing": "Lồng tiếng video",
            "Projects": "Dự án",
            "Batch": "Hàng loạt",
            "Settings": "Cài đặt",
            "Back": "Quay lại",
            "Close": "Đóng",
            "Cancel": "Hủy",
            "Continue": "Tiếp tục",
            "Browse": "Chọn thư mục",
            "Browse files": "Chọn tệp",
            "Refresh": "Làm mới",
            "More actions": "Thao tác khác",
            "More import options": "Tùy chọn thêm video",
            "From link": "Từ liên kết",
            "Add from link": "Thêm từ liên kết",
            "Import from link": "Nhập video từ liên kết",
            "YouTube, TikTok or Douyin": "YouTube, TikTok hoặc Douyin",
            "Video link": "Liên kết video",
            "Paste a video link": "Dán liên kết video",
            "Check link": "Kiểm tra liên kết",
            "Download and import": "Tải xuống và nhập",
            "Cancel download": "Hủy tải xuống",
            "Cancel download first": "Hủy tải xuống trước khi đóng",
            "Checking video link": "Đang kiểm tra liên kết video",
            "Video ready to download": "Video đã sẵn sàng để tải xuống",
            "Starting download": "Đang bắt đầu tải xuống",
            "Finalizing video": "Đang hoàn thiện video",
            "Download complete": "Đã tải xuống xong",
            "Cancelling download": "Đang hủy tải xuống",
            "Import cancelled": "Đã hủy nhập video",
            "Adding video to project": "Đang thêm video vào dự án",
            "Video added to project": "Đã thêm video vào dự án",
            "Paste a video link first.": "Hãy dán liên kết video trước.",
            "Enter a valid HTTP or HTTPS video link.": "Hãy nhập liên kết video HTTP hoặc HTTPS hợp lệ.",
            "Only YouTube, TikTok, and Douyin links are supported.": "Chỉ hỗ trợ liên kết YouTube, TikTok và Douyin.",
            "Paste a link to one video, not a playlist or channel.": "Hãy dán liên kết của một video, không phải danh sách phát hoặc kênh.",
            "Live and upcoming streams are not supported.": "Chưa hỗ trợ video trực tiếp hoặc sắp phát.",
            "Open or create a project before downloading a video.": "Hãy mở hoặc tạo dự án trước khi tải video.",
            "Pause or finish the current video before replacing it.": "Hãy tạm dừng hoặc hoàn tất video hiện tại trước khi thay thế.",

            "Create project": "Tạo dự án",
            "Project name": "Tên dự án",
            "Project storage location": "Vị trí lưu dự án",
            "Project type": "Loại dự án",
            "Single video": "Một video",
            "Batch videos": "Nhiều video",
            "New project": "Dự án mới",
            "Recent projects": "Dự án gần đây",
            "Create a project or reopen previous work.": "Tạo dự án mới hoặc tiếp tục dự án trước đó.",
            "Select a project to view its progress and exports.": "Chọn dự án để xem tiến trình và video xuất.",
            "Start with one source video": "Bắt đầu với một video nguồn",
            "Single video or batch": "Một video hoặc hàng loạt",
            "No preview": "Chưa có hình xem trước",

            "Queued": "Đang chờ",
            "In progress": "Đang thực hiện",
            "Processing": "Đang xử lý",
            "Complete": "Hoàn tất",
            "Failed": "Lỗi",
            "Cancelled": "Đã hủy",
            "Paused": "Đã tạm dừng",
            "Review needed": "Cần duyệt",
            "done": "Hoàn tất",
            "pending": "Đang chờ",
            "processing": "Đang xử lý",
            "failed": "Lỗi",
            "cancelled": "Đã hủy",
            "paused": "Đã tạm dừng",
            "awaiting_review": "Cần duyệt bản dịch",

            "Batch queue": "Hàng đợi xử lý",
            "Batch project": "Dự án hàng loạt",
            "Process a video collection with one shared dubbing setup.": "Xử lý nhiều video bằng một thiết lập lồng tiếng dùng chung.",
            "Clear": "Xóa danh sách",
            "Delete batch": "Xóa batch",
            "Add videos": "Thêm video",
            "Add folder": "Thêm thư mục",
            "Start queue": "Bắt đầu xử lý",
            "Stop queue": "Dừng hàng đợi",
            "Videos": "Video",
            "videos": "video",
            "Completed": "Hoàn tất",
            "Target": "Ngôn ngữ đích",
            "Mixed settings": "Thiết lập riêng theo video",
            "Queue processing": "Đang xử lý hàng đợi",
            "Overall progress": "Tiến độ tổng",
            "Drop videos into the queue": "Thả video vào hàng đợi",
            "Drop videos or a folder into the queue": "Thả video hoặc thư mục vào hàng đợi",
            "Release to add videos": "Thả để thêm video",
            "MP4, MOV or MKV; multiple files are supported": "Hỗ trợ nhiều tệp MP4, MOV hoặc MKV",
            "Only MP4, MOV and MKV files are added": "Chỉ thêm tệp MP4, MOV và MKV",
            "Browse folder": "Chọn thư mục",
            "Videos": "Video",
            "Your queue is empty": "Hàng đợi đang trống",
            "Add videos above to begin a batch": "Thêm video ở phía trên để bắt đầu xử lý",
            "items": "mục",
            "Batch settings": "Thiết lập hàng loạt",
            "Batch setup": "Thiết lập batch",
            "Configure this batch": "Thiết lập lồng tiếng và phụ đề cho batch này",
            "Configure dubbing and subtitle presets for this batch": "Thiết lập lồng tiếng và khung phụ đề cho hàng loạt video",
            "Dubbing and audio": "Lồng tiếng và âm thanh",
            "One subtitle frame is shared by each video size": "Mỗi kích thước video dùng chung một khung phụ đề",
            "Edit": "Chỉnh sửa",
            "Apply shared dubbing defaults to every video": "Áp dụng thiết lập lồng tiếng chung cho tất cả video",
            "Apply to all videos": "Áp dụng cho tất cả video",
            "Edit all subtitles": "Chỉnh phụ đề toàn bộ",
            "Subtitle presets by video size": "Khung phụ đề theo kích thước video",
            "Subtitle presets": "Khung phụ đề",
            "sizes": "kích thước",
            "custom": "tùy chỉnh",
            "Custom": "Tùy chỉnh",
            "Edit this size": "Chỉnh kích thước này",
            "Save video settings": "Lưu thiết lập video",
            "Unknown size": "Chưa xác định kích thước",

            "Prepare project": "Chuẩn bị dự án",
            "Extract audio": "Trích xuất âm thanh",
            "Separate vocals": "Tách giọng",
            "Transcribe speech": "Nhận diện lời nói",
            "Translate segments": "Dịch phụ đề",
            "Build subtitles": "Tạo phụ đề",
            "Generate voice": "Tạo giọng đọc",
            "Mix audio timeline": "Phối âm thanh",
            "Render final video": "Kết xuất video",
            "Finish": "Hoàn tất",

            "Create a new dub": "Tạo video lồng tiếng mới",
            "Turn one source video into a translated, voiced and captioned export.": "Chuyển video nguồn thành bản dịch, giọng đọc và phụ đề hoàn chỉnh.",
            "Source media": "Video nguồn",
            "Input video and subtitle placement": "Video đầu vào và vị trí phụ đề",
            "Select a source video": "Chọn video nguồn",
            "Drop video to import": "Thả video để nhập",
            "Release to add the source file": "Thả để thêm video nguồn",
            "Source imported": "Đã nhập video nguồn",
            "No source selected": "Chưa chọn video nguồn",
            "Choose a file to begin": "Chọn một tệp để bắt đầu",
            "Replace": "Thay thế",
            "Edit subtitle frame": "Chỉnh khung phụ đề",

            "Dubbing setup": "Thiết lập lồng tiếng",
            "Language, voice and output behavior": "Ngôn ngữ, giọng đọc và cách xử lý âm thanh",
            "Workflow": "Quy trình",
            "Full auto": "Tự động",
            "Review then dub": "Duyệt trước khi lồng tiếng",
            "Translate to": "Dịch sang",
            "Search language": "Tìm ngôn ngữ",
            "Voice": "Giọng đọc",
            "Separate vocals for music or noisy audio": "Tách giọng khi video có nhạc hoặc tạp âm",
            "Audio separation is slower in CPU mode": "Tách âm sẽ chậm hơn khi chạy bằng CPU",
            "Original audio": "Âm thanh gốc",
            "Audio source": "Nguồn âm thanh",
            "Keep original audio": "Giữ âm thanh gốc",
            "Original audio volume": "Âm lượng gốc",
            "Another project is already processing": "Một dự án khác đang được xử lý",
            "Add to processing queue": "Đưa vào hàng đợi xử lý",
            "Create and process": "Tạo và xử lý",
            "Process": "Xử lý",

            "Activity log": "Nhật ký hoạt động",
            "Live processing output": "Nhật ký xử lý trực tiếp",
            "Logs will appear here while this project is processing.": "Nhật ký sẽ xuất hiện tại đây khi dự án đang được xử lý.",
            "No logs loaded.": "Chưa có nhật ký.",

            "Ready to process": "Sẵn sàng xử lý",
            "Prepare project": "Chuẩn bị dự án",
            "Last export ready": "Video xuất đã sẵn sàng",
            "Ready": "Sẵn sàng",
            "No active job": "Không có video đang xử lý",
            "No video selected": "Chưa chọn video",
            "Settings applied": "Đã áp dụng cài đặt",
            "Settings reset to defaults": "Đã khôi phục cài đặt mặc định",
            "Switching processing device": "Đang chuyển thiết bị xử lý",
            "Preparing HY-MT2 translation model": "Đang chuẩn bị model dịch HY-MT2",
            "Preparing HY-MT2 translation": "Đang chuẩn bị dịch bằng HY-MT2",
            "Loading HY-MT2 translation model": "Đang tải model dịch HY-MT2",
            "Reusing HY-MT2 translation model": "Đang dùng lại model dịch HY-MT2",
            "Loading HY-MT2 tokenizer": "Đang tải bộ tách từ HY-MT2",
            "Loading HY-MT2 weights": "Đang tải trọng số HY-MT2",
            "HY-MT2 model is ready": "Model HY-MT2 đã sẵn sàng",
            "HY-MT2 Q4 CPU model is ready": "Model HY-MT2 Q4 cho CPU đã sẵn sàng",
            "Preparing job": "Đang chuẩn bị video",
            "Processing started": "Đã bắt đầu xử lý",
            "Queued to resume": "Đã đưa vào hàng đợi để tiếp tục",
            "Queued to restart": "Đã đưa vào hàng đợi để chạy lại",
            "Queued to create dub": "Đã đưa vào hàng đợi để tạo lồng tiếng",
            "Queued for processing": "Đã đưa vào hàng đợi xử lý",
            "Translation ready for review": "Bản dịch đã sẵn sàng để duyệt",
            "Extracting source audio": "Đang trích xuất âm thanh nguồn",
            "Source audio ready": "Âm thanh nguồn đã sẵn sàng",
            "Separating speech from background audio": "Đang tách lời nói khỏi âm thanh nền",
            "Speech track ready": "Âm thanh lời nói đã sẵn sàng",
            "Preparing speech recognition": "Đang chuẩn bị nhận diện lời nói",
            "Starting HY-MT2 translation": "Đang bắt đầu dịch bằng HY-MT2",
            "Reusing subtitles checkpoint": "Đang dùng lại checkpoint phụ đề",
            "Formatting timed subtitles": "Đang định dạng phụ đề theo thời gian",
            "Reusing generated voices": "Đang dùng lại giọng đọc đã tạo",
            "Starting voice synthesis": "Đang bắt đầu tạo giọng đọc",
            "Reusing mixed audio checkpoint": "Đang dùng lại checkpoint âm thanh",
            "Fitting voices to the video timeline": "Đang khớp giọng đọc với thời lượng video",
            "Reusing rendered video checkpoint": "Đang dùng lại checkpoint video đã kết xuất",
            "Rendering final video": "Đang kết xuất video đầu ra",
            "Preparing project": "Đang chuẩn bị dự án",
            "Extracting audio": "Đang trích xuất âm thanh",
            "Separating vocals": "Đang tách giọng",
            "Transcribing speech": "Đang nhận diện lời nói",
            "Translating": "Đang dịch",
            "Waiting for translation review": "Đang chờ duyệt bản dịch",
            "Creating subtitles": "Đang tạo phụ đề",
            "Generating voice": "Đang tạo giọng đọc",
            "Mixing audio": "Đang phối âm thanh",
            "Rendering video": "Đang kết xuất video",
            "Export complete": "Xuất video hoàn tất",
            "Final video ready": "Video đầu ra đã sẵn sàng",
            "Processing status will appear here": "Trạng thái xử lý sẽ xuất hiện tại đây",
            "Time running": "Thời gian đã chạy",
            "Processing time": "Thời gian xử lý",
            "Resume": "Tiếp tục",
            "Restart": "Chạy lại",
            "Pause": "Tạm dừng",
            "Review translation": "Duyệt bản dịch",
            "Open input video": "Mở video nguồn",
            "Open output video": "Mở video đầu ra",
            "Open export folder": "Mở thư mục video xuất",
            "Open project folder": "Mở thư mục dự án",
            "Remove video": "Xóa video",
            "Delete project": "Xóa dự án",

            "Appearance and language": "Giao diện và ngôn ngữ",
            "Appearance, language and performance": "Giao diện, ngôn ngữ và hiệu năng",
            "Theme": "Chủ đề",
            "Dark": "Tối",
            "Light": "Sáng",
            "Choose the application appearance": "Chọn giao diện hiển thị của ứng dụng",
            "Language": "Ngôn ngữ",
            "English": "Tiếng Anh",
            "Vietnamese": "Tiếng Việt",
            "Choose the interface language": "Chọn ngôn ngữ hiển thị",
            "Performance": "Hiệu năng",
            "Processing device": "Thiết bị xử lý",
            "Auto": "Tự động",
            "GPU": "GPU",
            "CPU": "CPU",
            "GPU accelerated": "Tăng tốc GPU",
            "GPU low memory": "GPU ít bộ nhớ",
            "CPU balanced": "CPU cân bằng",
            "CPU low memory": "CPU ít bộ nhớ",
            "CPU minimum memory": "CPU bộ nhớ tối thiểu",
            "Current hardware": "Cấu hình máy hiện tại",
            "Active GPU": "GPU đang hoạt động",
            "Active GPU role": "Vai trò GPU",
            "GPU compute": "Xử lý bằng GPU",
            "Windows display adapter": "GPU hiển thị Windows",
            "Display resolution": "Độ phân giải màn hình",
            "CPU cores": "Nhân CPU",
            "CPU max clock": "Xung CPU tối đa",
            "CPU clock": "Xung CPU",
            "GPU processing": "Đang xử lý bằng GPU",
            "CPU processing": "Đang xử lý bằng CPU",
            "GPU available": "GPU khả dụng",
            "Yes": "Có",
            "No": "Không",
            "cores": "nhân",
            "threads": "luồng",
            "No CUDA GPU detected": "Không phát hiện GPU CUDA",
            "Total VRAM": "VRAM tổng",
            "Free VRAM": "VRAM trống",
            "System RAM": "RAM hệ thống",
            "CPU threads": "Luồng CPU",
            "Power source": "Nguồn điện",
            "Plugged in": "Đang cắm sạc",
            "On battery": "Đang dùng pin",
            "Unknown": "Không rõ",
            "Recommended": "Khuyến nghị",
            "GPU memory is safe for processing": "Bộ nhớ GPU đủ an toàn để xử lý",
            "Automatic mode will use CPU when GPU memory is insufficient": "Chế độ tự động sẽ dùng CPU khi bộ nhớ GPU không đủ",
            "GPU is recommended for faster processing": "Khuyến nghị dùng GPU để xử lý nhanh hơn",
            "CPU is recommended while running on battery": "Khuyến nghị dùng CPU khi laptop đang chạy bằng pin",
            "CPU is recommended because GPU is unavailable or unsafe": "Khuyến nghị dùng CPU vì GPU không khả dụng hoặc chưa đủ an toàn",
            "Reset defaults": "Khôi phục mặc định",
            "Apply settings": "Áp dụng",

            "Approve and continue": "Duyệt và tiếp tục",
            "segments": "câu phụ đề",
            "Segment": "Câu",

            "Input Preview Editor": "Chỉnh khung phụ đề",
            "Subtitle frame editor": "Chỉnh khung phụ đề",
            "Video preview": "Xem trước video",
            "Subtitle placement": "Vị trí phụ đề",
            "Output preview": "Xem trước đầu ra",
            "Video timeline": "Dòng thời gian video",
            "Drag the frame or resize from any edge": "Kéo để di chuyển hoặc thay đổi kích thước từ các cạnh",
            "Review the rendered output": "Xem lại video đã xuất",
            "Play": "Phát",
            "Subtitle preview": "Phụ đề mẫu",
            "Apply to this size": "Áp dụng cho kích thước này",
            "Save subtitle frame": "Lưu khung phụ đề",
            "Not available": "Chưa có",
            "Open video": "Mở video"
        }
        return vi[source] || source
    }
}
