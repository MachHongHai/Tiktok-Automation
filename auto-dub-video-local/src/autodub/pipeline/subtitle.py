import datetime
import json
import srt
from autodub.services.job_store import log_to_job

def split_text_by_length(text: str, max_chars: int) -> str:
    """Wraps text into lines that do not exceed max_chars length."""
    words = text.split()
    lines = []
    current_line = []
    current_length = 0
    for word in words:
        word_len = len(word)
        added_len = word_len + (1 if current_line else 0)
        if current_length + added_len <= max_chars:
            current_line.append(word)
            current_length += added_len
        else:
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]
            current_length = word_len
    if current_line:
        lines.append(" ".join(current_line))
    return "\n".join(lines)

def generate_srt(segments_json_path: str, output_srt_path: str, max_chars_per_line: int, job_id: str):
    """Loads segments and writes an SRT subtitle file."""
    log_to_job(job_id, f"Compiling SRT file (Max characters per line: {max_chars_per_line})...")
    
    with open(segments_json_path, "r", encoding="utf-8") as f:
        segments = json.load(f)
        
    subtitles = []
    for idx, seg in enumerate(segments, 1):
        start_sec = seg["start"]
        end_sec = seg["end"]
        text = seg["text"]
        
        # Split text lines safely
        formatted_text = split_text_by_length(text, max_chars_per_line)
        
        sub = srt.Subtitle(
            index=idx,
            start=datetime.timedelta(seconds=start_sec),
            end=datetime.timedelta(seconds=end_sec),
            content=formatted_text
        )
        subtitles.append(sub)
        
    srt_content = srt.compose(subtitles)
    with open(output_srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)
        
    log_to_job(job_id, f"Saved subtitles to: {output_srt_path}")

def parse_srt_to_segments(srt_path: str) -> list:
    """Parses an SRT file and returns a list of segment dicts (start, end, text)."""
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()
        
    subtitles = list(srt.parse(content))
    segments = []
    for sub in subtitles:
        start_sec = sub.start.total_seconds()
        end_sec = sub.end.total_seconds()
        
        # Replace newlines with spaces for TTS processing
        clean_text = " ".join(sub.content.replace("\n", " ").split()).strip()
        segments.append({
            "start": round(start_sec, 3),
            "end": round(end_sec, 3),
            "text": clean_text
        })
    return segments

