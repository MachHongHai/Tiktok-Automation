from pydantic import BaseModel, Field
from typing import Dict, Literal, Optional


VIDEO_METADATA_SCHEMA_VERSION = 4
VIDEO_METADATA_TYPE = "haizflow.video"


class MediaSource(BaseModel):
    type: Literal["local_file", "video_url", "channel"] = "local_file"
    platform: str = ""
    remote_video_id: str = ""
    source_url: str = ""
    channel_url: str = ""
    channel_name: str = ""
    import_session_id: str = ""
    imported_at: str = ""


class SubtitleStyle(BaseModel):
    font_size: int = 14
    margin_bottom: int = 40
    outline: int = 2
    max_chars_per_line: int = 32
    position_x_percent: int = 50
    position_y_percent: int = 88
    box_width_percent: int = 72
    box_height_percent: int = 12


class CropSettings(BaseModel):
    zoom_percent: int = 100
    pan_x_percent: int = 0
    pan_y_percent: int = 0
    left_percent: int = 0
    right_percent: int = 0
    top_percent: int = 0
    bottom_percent: int = 0


class JobConfig(BaseModel):
    mode: str = "A"  # A = full auto, review = pause after translation.
    source_language: str = "auto"  # Automatic detection is performed for every speech segment.
    target_language: str = "vi"
    translator_provider: str = "hymt2"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    output_format: str = "keep_ratio"  # The desktop workflow preserves the original aspect ratio.
    crop: CropSettings = Field(default_factory=CropSettings)
    enable_audio_separation: bool = False
    original_video_volume: int = 60
    project_name: str = ""
    project_directory: str = ""
    project_type: str = "single"
    project_id: str = ""
    project_key: str = ""
    review_approved: bool = False


class JobInfo(BaseModel):
    schema_version: int = VIDEO_METADATA_SCHEMA_VERSION
    metadata_type: str = VIDEO_METADATA_TYPE
    job_id: str
    original_filename: str
    mode: str
    source_language: str
    target_language: str
    translator_provider: str = "hymt2"
    tts_voice: str
    subtitle_style: SubtitleStyle
    output_format: str
    crop: CropSettings = Field(default_factory=CropSettings)
    enable_audio_separation: bool = False
    original_video_volume: int = 60
    project_name: str = ""
    project_directory: str = ""
    project_type: str = "single"
    project_id: str = ""
    project_key: str = ""
    video_width: int = 0
    video_height: int = 0
    subtitle_override: bool = False
    review_approved: bool = False
    media_source: MediaSource = Field(default_factory=MediaSource)
    status: str  # pending, processing, done, failed
    progress: int = 0
    step: str = "pending"
    resume_step: str = ""
    # Separate from pause/resume checkpoints: this records a single automatic
    # GPU-to-CPU recovery during the current run.
    runtime_recovery_step: str = ""
    gpu_recovery_attempted: bool = False
    checkpoints: Dict[str, str] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    started_at: Optional[str] = None
    estimated_remaining_seconds: Optional[int] = None
    step_detail: str = ""
    current_item: int = 0
    total_items: int = 0
    error: Optional[str] = None
    files: Dict[str, Optional[str]] = Field(default_factory=dict)
