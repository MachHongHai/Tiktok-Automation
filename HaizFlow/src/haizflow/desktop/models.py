"""Qt list models used by the QML presentation layer."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from haizflow.desktop.media import thumbnail_source

class VideoListModel(QAbstractListModel):
    VideoIdRole = Qt.ItemDataRole.UserRole + 1
    FileRole = Qt.ItemDataRole.UserRole + 2
    ModeRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    StepRole = Qt.ItemDataRole.UserRole + 5
    UpdatedRole = Qt.ItemDataRole.UserRole + 6
    ProgressRole = Qt.ItemDataRole.UserRole + 7
    ThumbnailRole = Qt.ItemDataRole.UserRole + 8
    ProjectNameRole = Qt.ItemDataRole.UserRole + 9
    VideoSizeRole = Qt.ItemDataRole.UserRole + 10
    SubtitleOverrideRole = Qt.ItemDataRole.UserRole + 11

    def __init__(self):
        super().__init__()
        self._videos = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._videos)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._videos):
            return None
        video = self._videos[index.row()]
        return {
            self.VideoIdRole: video.video_id,
            self.FileRole: video.original_filename,
            self.ModeRole: "Full Auto",
            self.StatusRole: video.status,
            self.StepRole: video.step,
            self.UpdatedRole: video.updated_at,
            self.ProgressRole: video.progress,
            self.ThumbnailRole: self._thumbnail_source(video),
            self.ProjectNameRole: video.project_name or video.original_filename,
            self.VideoSizeRole: self._video_size(video),
            self.SubtitleOverrideRole: bool(getattr(video, "subtitle_override", False)),
        }.get(role)

    def roleNames(self):
        return {
            self.VideoIdRole: b"videoId",
            self.FileRole: b"fileName",
            self.ModeRole: b"mode",
            self.StatusRole: b"status",
            self.StepRole: b"step",
            self.UpdatedRole: b"updatedAt",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
            self.ProjectNameRole: b"projectName",
            self.VideoSizeRole: b"videoSize",
            self.SubtitleOverrideRole: b"subtitleOverride",
        }

    def set_videos(self, videos):
        current_ids = [video.video_id for video in self._videos]
        next_ids = [video.video_id for video in videos]
        if current_ids == next_ids:
            self._videos = videos
            if videos:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(videos) - 1, 0),
                    list(self.roleNames().keys()),
                )
            return
        self.beginResetModel()
        self._videos = videos
        self.endResetModel()

    def video_at(self, row: int):
        if row < 0 or row >= len(self._videos):
            return None
        return self._videos[row]

    @staticmethod
    def _thumbnail_source(video):
        path = video.files.get("thumbnail") if video else ""
        return thumbnail_source(path)

    @staticmethod
    def _video_size(video):
        width = int(getattr(video, "video_width", 0) or 0)
        height = int(getattr(video, "video_height", 0) or 0)
        return f"{width} x {height}" if width and height else "Unknown size"


class ProjectListModel(QAbstractListModel):
    ProjectNameRole = Qt.ItemDataRole.UserRole + 1
    ProjectTypeRole = Qt.ItemDataRole.UserRole + 2
    VideoCountRole = Qt.ItemDataRole.UserRole + 3
    StatusRole = Qt.ItemDataRole.UserRole + 4
    ProgressRole = Qt.ItemDataRole.UserRole + 5
    ThumbnailRole = Qt.ItemDataRole.UserRole + 6

    def __init__(self):
        super().__init__()
        self._projects = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._projects)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._projects):
            return None
        project = self._projects[index.row()]
        return {
            self.ProjectNameRole: project["project_name"],
            self.ProjectTypeRole: project["project_type"],
            self.VideoCountRole: project["video_count"],
            self.StatusRole: project["status"],
            self.ProgressRole: project["progress"],
            self.ThumbnailRole: project["thumbnail_source"],
        }.get(role)

    def roleNames(self):
        return {
            self.ProjectNameRole: b"projectName",
            self.ProjectTypeRole: b"projectType",
            self.VideoCountRole: b"videoCount",
            self.StatusRole: b"status",
            self.ProgressRole: b"progress",
            self.ThumbnailRole: b"thumbnailSource",
        }

    def set_projects(self, projects):
        next_keys = [project["key"] for project in projects]
        current_keys = [project["key"] for project in self._projects]
        if current_keys == next_keys:
            self._projects = projects
            if projects:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(projects) - 1, 0),
                    list(self.roleNames().keys()),
                )
            return
        self.beginResetModel()
        self._projects = projects
        self.endResetModel()

    def project_at(self, row: int):
        if row < 0 or row >= len(self._projects):
            return None
        return self._projects[row]


class ChannelCandidateListModel(QAbstractListModel):
    CandidateIdRole = Qt.ItemDataRole.UserRole + 1
    SelectedRole = Qt.ItemDataRole.UserRole + 2
    TitleRole = Qt.ItemDataRole.UserRole + 3
    PlatformRole = Qt.ItemDataRole.UserRole + 4
    UploaderRole = Qt.ItemDataRole.UserRole + 5
    DurationRole = Qt.ItemDataRole.UserRole + 6
    PublishedRole = Qt.ItemDataRole.UserRole + 7
    ViewCountRole = Qt.ItemDataRole.UserRole + 8
    ThumbnailRole = Qt.ItemDataRole.UserRole + 9
    DuplicateRole = Qt.ItemDataRole.UserRole + 10
    StatusRole = Qt.ItemDataRole.UserRole + 11
    ProgressRole = Qt.ItemDataRole.UserRole + 12
    ErrorRole = Qt.ItemDataRole.UserRole + 13

    def __init__(self):
        super().__init__()
        self._candidates = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._candidates)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._candidates):
            return None
        candidate = self._candidates[index.row()]
        return {
            self.CandidateIdRole: candidate.remote_video_id,
            self.SelectedRole: candidate.selected,
            self.TitleRole: candidate.title,
            self.PlatformRole: candidate.platform,
            self.UploaderRole: candidate.uploader,
            self.DurationRole: candidate.duration_label,
            self.PublishedRole: candidate.published_label,
            self.ViewCountRole: candidate.view_count_label,
            self.ThumbnailRole: candidate.thumbnail_url,
            self.DuplicateRole: candidate.duplicate,
            self.StatusRole: candidate.status,
            self.ProgressRole: candidate.progress,
            self.ErrorRole: candidate.error,
        }.get(role)

    def roleNames(self):
        return {
            self.CandidateIdRole: b"candidateId",
            self.SelectedRole: b"selected",
            self.TitleRole: b"title",
            self.PlatformRole: b"platform",
            self.UploaderRole: b"uploader",
            self.DurationRole: b"durationLabel",
            self.PublishedRole: b"publishedLabel",
            self.ViewCountRole: b"viewCountLabel",
            self.ThumbnailRole: b"thumbnailSource",
            self.DuplicateRole: b"duplicate",
            self.StatusRole: b"candidateStatus",
            self.ProgressRole: b"candidateProgress",
            self.ErrorRole: b"candidateError",
        }

    def set_candidates(self, candidates):
        self.beginResetModel()
        self._candidates = list(candidates)
        self.endResetModel()

    def candidate_at(self, row: int):
        if row < 0 or row >= len(self._candidates):
            return None
        return self._candidates[row]

    def candidates(self):
        return list(self._candidates)

    def update_candidate(self, remote_video_id: str) -> None:
        for row, candidate in enumerate(self._candidates):
            if candidate.remote_video_id == remote_video_id:
                index = self.index(row, 0)
                self.dataChanged.emit(index, index, list(self.roleNames().keys()))
                return


class TaskListModel(QAbstractListModel):
    NameRole = Qt.ItemDataRole.UserRole + 1
    KeyRole = Qt.ItemDataRole.UserRole + 2
    StateRole = Qt.ItemDataRole.UserRole + 3
    DetailRole = Qt.ItemDataRole.UserRole + 4

    STEPS = [
        ("starting", "Prepare project"),
        ("extracting_audio", "Extract audio"),
        ("separating_audio", "Separate vocals"),
        ("transcribing", "Transcribe speech"),
        ("translating", "Translate segments"),
        ("creating_subtitle", "Build subtitles"),
        ("creating_voice", "Generate voice"),
        ("building_audio_timeline", "Mix audio timeline"),
        ("rendering", "Render final video"),
        ("done", "Finish"),
    ]

    def __init__(self):
        super().__init__()
        self._tasks = self._build_tasks(None)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._tasks)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._tasks):
            return None
        task = self._tasks[index.row()]
        return {
            self.NameRole: task["name"],
            self.KeyRole: task["key"],
            self.StateRole: task["state"],
            self.DetailRole: task["detail"],
        }.get(role)

    def roleNames(self):
        return {
            self.NameRole: b"name",
            self.KeyRole: b"key",
            self.StateRole: b"taskState",
            self.DetailRole: b"detail",
        }

    def set_video(self, video):
        self.beginResetModel()
        self._tasks = self._build_tasks(video)
        self.endResetModel()

    def _build_tasks(self, video):
        current_step = video.step if video else "pending"
        status = video.status if video else "pending"
        step_keys = [key for key, _name in self.STEPS]
        current_index = step_keys.index(current_step) if current_step in step_keys else -1
        tasks = []
        for index, (key, name) in enumerate(self.STEPS):
            if not video:
                state = "pending"
            elif status == "done":
                state = "done"
            elif status in {"failed", "cancelled"} and (key == current_step or index == max(current_index, 0)):
                state = status
            elif index < current_index:
                state = "done"
            elif index == current_index and status == "processing":
                state = "active"
            else:
                state = "pending"
            tasks.append({"key": key, "name": name, "state": state, "detail": key.replace("_", " ")})
        return tasks
