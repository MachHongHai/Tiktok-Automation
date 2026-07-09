from pydantic import BaseModel, Field
from typing import Optional, Dict

class SubtitleStyle(BaseModel):
    font_size: int = 14
    margin_bottom: int = 40
    outline: int = 2
    max_chars_per_line: int = 32

class JobConfig(BaseModel):
    mode: str = "A"  # A, B, C
    source_language: str = "auto"  # zh, en, auto
    target_language: str = "vi"
    tts_voice: str = "vi-VN-HoaiMyNeural"
    subtitle_style: SubtitleStyle = Field(default_factory=SubtitleStyle)
    output_format: str = "keep_ratio"  # tiktok_9_16_crop, keep_ratio, blur_background_9_16
    enable_audio_separation: bool = True
    original_video_volume: int = 60

class JobInfo(BaseModel):
    job_id: str
    original_filename: str
    mode: str
    source_language: str
    target_language: str
    tts_voice: str
    subtitle_style: SubtitleStyle
    output_format: str
    enable_audio_separation: bool = True
    original_video_volume: int = 60
    status: str  # pending, processing, done, failed
    progress: int = 0
    step: str = "pending"
    created_at: str
    updated_at: str
    error: Optional[str] = None
    files: Dict[str, Optional[str]] = Field(default_factory=dict)
