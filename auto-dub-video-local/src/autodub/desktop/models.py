"""Qt list models used by the QML presentation layer."""

from PySide6.QtCore import QAbstractListModel, QModelIndex, Qt

from autodub.desktop.media import thumbnail_source

class JobListModel(QAbstractListModel):
    JobIdRole = Qt.ItemDataRole.UserRole + 1
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
        self._jobs = []

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._jobs)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or index.row() < 0 or index.row() >= len(self._jobs):
            return None
        job = self._jobs[index.row()]
        return {
            self.JobIdRole: job.job_id,
            self.FileRole: job.original_filename,
            self.ModeRole: "Full Auto",
            self.StatusRole: job.status,
            self.StepRole: job.step,
            self.UpdatedRole: job.updated_at,
            self.ProgressRole: job.progress,
            self.ThumbnailRole: self._thumbnail_source(job),
            self.ProjectNameRole: job.project_name or job.original_filename,
            self.VideoSizeRole: self._video_size(job),
            self.SubtitleOverrideRole: bool(getattr(job, "subtitle_override", False)),
        }.get(role)

    def roleNames(self):
        return {
            self.JobIdRole: b"jobId",
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

    def set_jobs(self, jobs):
        current_ids = [job.job_id for job in self._jobs]
        next_ids = [job.job_id for job in jobs]
        if current_ids == next_ids:
            self._jobs = jobs
            if jobs:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(len(jobs) - 1, 0),
                    list(self.roleNames().keys()),
                )
            return
        self.beginResetModel()
        self._jobs = jobs
        self.endResetModel()

    def job_at(self, row: int):
        if row < 0 or row >= len(self._jobs):
            return None
        return self._jobs[row]

    @staticmethod
    def _thumbnail_source(job):
        path = job.files.get("thumbnail") if job else ""
        return thumbnail_source(path)

    @staticmethod
    def _video_size(job):
        width = int(getattr(job, "video_width", 0) or 0)
        height = int(getattr(job, "video_height", 0) or 0)
        return f"{width} x {height}" if width and height else "Unknown size"


class ProjectListModel(QAbstractListModel):
    ProjectNameRole = Qt.ItemDataRole.UserRole + 1
    ProjectTypeRole = Qt.ItemDataRole.UserRole + 2
    JobCountRole = Qt.ItemDataRole.UserRole + 3
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
            self.JobCountRole: project["job_count"],
            self.StatusRole: project["status"],
            self.ProgressRole: project["progress"],
            self.ThumbnailRole: project["thumbnail_source"],
        }.get(role)

    def roleNames(self):
        return {
            self.ProjectNameRole: b"projectName",
            self.ProjectTypeRole: b"projectType",
            self.JobCountRole: b"jobCount",
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

    def set_job(self, job):
        self.beginResetModel()
        self._tasks = self._build_tasks(job)
        self.endResetModel()

    def _build_tasks(self, job):
        current_step = job.step if job else "pending"
        status = job.status if job else "pending"
        step_keys = [key for key, _name in self.STEPS]
        current_index = step_keys.index(current_step) if current_step in step_keys else -1
        tasks = []
        for index, (key, name) in enumerate(self.STEPS):
            if not job:
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
