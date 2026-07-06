def seconds_to_srt_timestamp(seconds: float) -> str:
    """Converts a float number of seconds to SRT subtitle format: HH:MM:SS,mmm"""
    if seconds < 0:
        seconds = 0.0
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    milliseconds = int(round((seconds - int(seconds)) * 1000))
    
    # Handle rounding overflows
    if milliseconds >= 1000:
        secs += 1
        milliseconds -= 1000
    if secs >= 60:
        minutes += 1
        secs -= 60
    if minutes >= 60:
        hours += 1
        minutes -= 60
        
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{milliseconds:03d}"
