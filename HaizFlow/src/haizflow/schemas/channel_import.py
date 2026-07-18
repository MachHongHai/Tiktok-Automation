from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field


class ChannelImportRequest(BaseModel):
    url: str
    platform: Literal["", "youtube", "tiktok", "douyin"] = ""
    ranking: Literal["newest", "popular"] = "newest"
    limit: int = Field(default=20, ge=1, le=100)
    duration_filter: Literal["all", "short", "long"] = "short"
    scan_scope: int = Field(default=300, ge=0, le=10000)
    cookie_browser: str = Field(default="", exclude=True)
    cookie_file: str = Field(default="", exclude=True)


class ChannelVideoCandidate(BaseModel):
    remote_video_id: str
    source_url: str
    title: str
    platform: str
    # YouTube exposes regular videos and Shorts through separate channel tabs.
    # Keep that provenance so their classification does not depend on duration.
    content_type: Literal["", "short", "long"] = ""
    uploader: str = ""
    duration_seconds: int = 0
    published_at: str = ""
    view_count: int | None = None
    thumbnail_url: str = ""
    selected: bool = True
    duplicate: bool = False
    status: str = "ready"
    progress: int = 0
    error: str = ""

    @property
    def duration_label(self) -> str:
        seconds = max(0, int(self.duration_seconds or 0))
        hours, remainder = divmod(seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"

    @property
    def published_label(self) -> str:
        value = str(self.published_at or "")
        if len(value) == 8 and value.isdigit():
            return f"{value[:4]}-{value[4:6]}-{value[6:]}"
        return value

    @property
    def view_count_label(self) -> str:
        if self.view_count is None:
            return "-"
        count = max(0, int(self.view_count))
        if count >= 1_000_000_000:
            return f"{count / 1_000_000_000:.1f}B".replace(".0B", "B")
        if count >= 1_000_000:
            return f"{count / 1_000_000:.1f}M".replace(".0M", "M")
        if count >= 1_000:
            return f"{count / 1_000:.1f}K".replace(".0K", "K")
        return str(count)


class ChannelImportSession(BaseModel):
    schema_version: int = 1
    session_id: str
    project_key: str
    project_root: str
    channel_url: str
    channel_name: str = ""
    platform: str = ""
    request: dict = Field(default_factory=dict)
    candidates: list[ChannelVideoCandidate] = Field(default_factory=list)
    state: str = "idle"
    status: str = ""
    created_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
    updated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    )
