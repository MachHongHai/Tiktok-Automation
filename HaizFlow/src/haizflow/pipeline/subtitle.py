import datetime
import json
import re

import srt

from haizflow.services.video_store import log_to_video


def split_text_by_length(text: str, max_chars: int) -> str:
    """Wrap one subtitle cue into at most two readable lines."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        added_length = len(word) + (1 if current else 0)
        if current and current_length + added_length > max_chars:
            lines.append(" ".join(current))
            current, current_length = [word], len(word)
        else:
            current.append(word)
            current_length += added_length
    if current:
        lines.append(" ".join(current))
    return "\n".join(lines)


def split_segment_into_cues(segment: dict, max_chars_per_line: int) -> list[dict]:
    """Split a transcript block into short sequential cues for social-video captions."""
    text = " ".join(segment.get("text", "").split())
    start = float(segment.get("start", 0))
    end = max(start, float(segment.get("end", start)))
    words = text.split()
    if not words:
        return []

    line_limit = max(12, max_chars_per_line)
    cue_limit = min(42, line_limit * 2)
    max_words = max(3, min(8, cue_limit // 5))
    chunks: list[list[str]] = []
    current: list[str] = []
    current_length = 0
    for word in words:
        added_length = len(word) + (1 if current else 0)
        candidate = " ".join([*current, word])
        would_need_three_lines = split_text_by_length(candidate, line_limit).count("\n") >= 2
        should_break = current and (current_length + added_length > cue_limit or len(current) >= max_words or would_need_three_lines)
        if should_break:
            chunks.append(current)
            current, current_length = [], 0
        current.append(word)
        current_length += len(word) + (1 if len(current) > 1 else 0)
        if len(current) >= 3 and re.search(r"[.!?;:]$", word):
            chunks.append(current)
            current, current_length = [], 0
    if current:
        chunks.append(current)

    total_weight = sum(max(1, len(" ".join(chunk))) for chunk in chunks)
    duration = max(0.3, end - start)
    cursor = start
    cues: list[dict] = []
    for index, chunk in enumerate(chunks):
        weight = max(1, len(" ".join(chunk)))
        cue_end = end if index == len(chunks) - 1 else cursor + duration * weight / total_weight
        cues.append({
            "start": round(cursor, 3),
            "end": round(max(cursor + 0.1, cue_end), 3),
            "text": split_text_by_length(" ".join(chunk), line_limit),
        })
        cursor = cue_end
    return cues


def generate_srt(segments_json_path: str, output_srt_path: str, max_chars_per_line: int, video_id: str):
    """Write short, timed subtitle cues instead of keeping each transcript block on screen."""
    log_to_video(video_id, f"Compiling sequential SRT cues (Max characters per line: {max_chars_per_line})...")
    with open(segments_json_path, "r", encoding="utf-8") as file:
        segments = json.load(file)

    subtitles = []
    for segment in segments:
        for cue in split_segment_into_cues(segment, max_chars_per_line):
            subtitles.append(srt.Subtitle(
                index=len(subtitles) + 1,
                start=datetime.timedelta(seconds=cue["start"]),
                end=datetime.timedelta(seconds=cue["end"]),
                content=cue["text"],
            ))
    with open(output_srt_path, "w", encoding="utf-8") as file:
        file.write(srt.compose(subtitles))
    log_to_video(video_id, f"Saved {len(subtitles)} sequential subtitle cues to: {output_srt_path}")


def parse_srt_to_segments(srt_path: str) -> list:
    """Parse an input SRT into normalized timestamped text segments."""
    with open(srt_path, "r", encoding="utf-8") as file:
        subtitles = list(srt.parse(file.read()))
    return [{
        "start": round(sub.start.total_seconds(), 3),
        "end": round(sub.end.total_seconds(), 3),
        "text": " ".join(sub.content.replace("\n", " ").split()).strip(),
    } for sub in subtitles]
