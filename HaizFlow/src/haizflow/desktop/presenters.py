"""Pure presentation mapping shared by the desktop controller and tests."""

import os

from haizflow.desktop.catalog import EDGE_TTS_VOICES_BY_LANGUAGE, POPULAR_TARGET_LANGUAGES
from haizflow.desktop.models import VideoListModel
from haizflow.services import project_store


VIETNAMESE_LANGUAGE_NAMES = {
    "vi": "Tiếng Việt",
    "en": "Tiếng Anh",
    "zh": "Tiếng Trung",
    "hi": "Tiếng Hindi",
    "es": "Tiếng Tây Ban Nha",
    "fr": "Tiếng Pháp",
    "ar": "Tiếng Ả Rập",
    "pt": "Tiếng Bồ Đào Nha",
    "ru": "Tiếng Nga",
    "id": "Tiếng Indonesia",
    "de": "Tiếng Đức",
    "ja": "Tiếng Nhật",
    "ko": "Tiếng Hàn",
    "it": "Tiếng Ý",
    "th": "Tiếng Thái",
    "fil": "Tiếng Filipino",
}


def build_project_summaries(videos, persisted_projects=None):
    grouped = {}
    for persisted in persisted_projects or []:
        key = persisted.get("key")
        if not key:
            continue
        grouped[key] = {
            "key": key,
            "project_name": persisted["project_name"],
            "project_directory": persisted.get("project_directory", ""),
            "project_type": "batch" if persisted.get("project_type") == "batch" else "single",
            "videos": [],
            "updated_at": persisted.get("updated_at", ""),
        }
    for video in videos:
        project_type = "batch" if getattr(video, "project_type", "single") == "batch" else "single"
        project_name = video.project_name or os.path.splitext(video.original_filename)[0]
        project_directory = video.project_directory or ""
        key = str(getattr(video, "project_key", "") or "")
        # A persisted video is migrated to an immutable project key when it is
        # read.  Plain presenter test data and truly legacy videos still need a
        # deterministic grouping key without consulting unrelated app data.
        if not key and project_directory:
            key = project_store.project_key(project_name, project_directory, project_type)
        if not key:
            key = f"legacy:{video.video_id}"
        project = grouped.setdefault(
            key,
            {
                "key": key,
                "project_name": project_name,
                "project_directory": project_directory,
                "project_type": project_type,
                "videos": [],
                "updated_at": video.updated_at,
            },
        )
        project["videos"].append(video)

    summaries = []
    for project in grouped.values():
        project_videos = project["videos"]
        if not project_videos:
            summaries.append(
                {
                    **project,
                    "video_count": 0,
                    "status": "empty",
                    "progress": 0,
                    "thumbnail_source": "",
                    "updated_at": project.get("updated_at", ""),
                }
            )
            continue
        statuses = {video.status for video in project_videos}
        if "processing" in statuses:
            status = "processing"
        elif "awaiting_review" in statuses:
            status = "awaiting_review"
        elif "paused" in statuses:
            status = "paused"
        elif "pending" in statuses:
            status = "pending"
        elif all(video.status == "done" for video in project_videos):
            status = "done"
        elif "failed" in statuses:
            status = "failed"
        elif "cancelled" in statuses:
            status = "cancelled"
        else:
            status = project_videos[0].status
        thumbnail_source = ""
        for video in project_videos:
            thumbnail_source = VideoListModel._thumbnail_source(video)
            if thumbnail_source:
                break
        summaries.append(
            {
                **project,
                "video_count": len(project_videos),
                "status": status,
                "progress": round(sum(video.progress for video in project_videos) / len(project_videos)),
                "thumbnail_source": thumbnail_source,
                "updated_at": max(video.updated_at for video in project_videos),
            }
        )
    return sorted(summaries, key=lambda project: project["updated_at"], reverse=True)


def language_label(code: str, ui_language: str) -> str:
    for language_code, english_name, native_name in POPULAR_TARGET_LANGUAGES:
        if language_code == code:
            if ui_language == "vi":
                return f"{VIETNAMESE_LANGUAGE_NAMES.get(language_code, native_name)} ({language_code})"
            return f"{english_name} ({language_code})"
    return code


def format_duration(seconds) -> str:
    seconds = max(0, round(seconds))
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}:{minutes:02}:{seconds:02}"
    return f"{minutes}:{seconds:02}"


def format_memory_size(value: int) -> str:
    if not value:
        return "--"
    return f"{value / (1024 ** 3):.1f} GB"


def voice_options_for_language(language_code: str, ui_language: str):
    voices = EDGE_TTS_VOICES_BY_LANGUAGE.get(language_code) or EDGE_TTS_VOICES_BY_LANGUAGE["en"]
    return [
        {
            "voice": voice,
            "label": f"{localized_voice_label(label, ui_language)} ({voice})",
        }
        for voice, label in voices
    ]


def localized_voice_label(label: str, ui_language: str) -> str:
    if ui_language != "vi":
        return label
    return label.replace("Female", "Nữ").replace("Male", "Nam")
