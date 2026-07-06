import app.config  # Import config first to load .env variables (HF_HOME, TORCH_HOME) before other imports
import os
import uuid
import shutil
from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from typing import Optional, List

from app.models import JobConfig, SubtitleStyle, JobInfo
from app.utils.ffmpeg import is_ffmpeg_available, get_ffmpeg_version
from app import job_store
from app.pipeline.process_job import process_job_sync

app = FastAPI(
    title="Auto Dub Video Local API",
    description="Local pipeline API for importing video, transcribing, translating, generating voices, and rendering dubbed videos.",
    version="1.0.0"
)

# Enable CORS for frontend client
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
def startup_event():
    """Validates if FFmpeg is present in the PATH on app startup."""
    if not is_ffmpeg_available():
        error_msg = (
            "\n" + "="*80 + "\n"
            " ERROR: FFmpeg or FFprobe is NOT installed or not added to your system PATH.\n"
            " Please install FFmpeg and make sure both 'ffmpeg' and 'ffprobe' commands run in your shell.\n"
            "="*80 + "\n"
        )
        print(error_msg)
        raise RuntimeError("FFmpeg and FFprobe must be installed and added to the PATH.")
    else:
        print("\n" + "="*80)
        print(" FFmpeg environment verified successfully.")
        print(f" {get_ffmpeg_version()}")
        print("="*80 + "\n")

@app.post("/api/jobs", response_model=JobInfo)
async def create_job(
    video: UploadFile = File(...),
    srt_file: Optional[UploadFile] = File(None),
    script_file: Optional[UploadFile] = File(None),
    mode: str = Form("A"),
    source_language: str = Form("auto"),
    target_language: str = Form("vi"),
    tts_voice: str = Form("vi-VN-HoaiMyNeural"),
    output_format: str = Form("keep_ratio"),
    font_size: int = Form(14),
    margin_bottom: int = Form(40),
    outline: int = Form(2),
    max_chars_per_line: int = Form(32),
    enable_audio_separation: bool = Form(True),
    original_video_volume: int = Form(60)
):
    # Validate uploaded file format
    ext = os.path.splitext(video.filename)[1].lower()
    if ext not in [".mp4", ".mov", ".mkv"]:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported video file extension '{ext}'. Only .mp4, .mov, and .mkv are supported."
        )
        
    job_id = str(uuid.uuid4())
    
    # Assemble subtitle configs
    subtitle_style = SubtitleStyle(
        font_size=font_size,
        margin_bottom=margin_bottom,
        outline=outline,
        max_chars_per_line=max_chars_per_line
    )
    job_config = JobConfig(
        mode=mode,
        source_language=source_language,
        target_language=target_language,
        tts_voice=tts_voice,
        subtitle_style=subtitle_style,
        output_format=output_format,
        enable_audio_separation=enable_audio_separation,
        original_video_volume=original_video_volume
    )
    
    # Write empty job directory structure and retrieve initial job.json
    job_info = job_store.create_job(job_id, video.filename, job_config)
    job_dir = job_store.get_job_dir(job_id)
    
    # Save the input video
    video_dest = job_info.files["video_input"]
    with open(video_dest, "wb") as buffer:
        shutil.copyfileobj(video.file, buffer)
        
    # Save optional Vietnamese subtitles file (Mode B)
    if srt_file and srt_file.filename:
        srt_dest = os.path.join(job_dir, "input", "vi.srt")
        with open(srt_dest, "wb") as buffer:
            shutil.copyfileobj(srt_file.file, buffer)
        job_info.files["srt_input"] = srt_dest
        
    # Save optional Vietnamese script file (Mode C)
    if script_file and script_file.filename:
        script_dest = os.path.join(job_dir, "input", "script_vi.txt")
        with open(script_dest, "wb") as buffer:
            shutil.copyfileobj(script_file.file, buffer)
        job_info.files["script_input"] = script_dest
        
    # Persist updated paths
    job_store.save_job(job_info)
    
    job_store.log_to_job(job_id, f"Uploaded input video: {video.filename}")
    if srt_file and srt_file.filename:
        job_store.log_to_job(job_id, f"Uploaded subtitle file: {srt_file.filename}")
    if script_file and script_file.filename:
        job_store.log_to_job(job_id, f"Uploaded script file: {script_file.filename}")
        
    return job_info

@app.get("/api/jobs", response_model=List[JobInfo])
def get_jobs_list():
    return job_store.list_jobs()

@app.get("/api/jobs/{job_id}", response_model=JobInfo)
def get_job_status(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    return job

@app.post("/api/jobs/{job_id}/process", response_model=JobInfo)
def trigger_process_job(job_id: str, background_tasks: BackgroundTasks):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
        
    if job.status == "processing":
        raise HTTPException(status_code=400, detail="This job is already being processed.")
        
    # Enqueue pipeline run on BackgroundTasks threads pool
    background_tasks.add_task(process_job_sync, job_id)
    
    # Return scheduled status
    job = job_store.update_job(job_id, status="processing", step="scheduled")
    return job

@app.get("/api/jobs/{job_id}/download/final")
def download_final_video(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    path = job.files.get("final_video")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Final processed video is not available yet.")
    return FileResponse(path, filename="final.mp4", media_type="video/mp4")

@app.get("/api/jobs/{job_id}/download/subtitle")
def download_subtitles(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    path = job.files.get("srt_output")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Subtitles have not been generated yet.")
    return FileResponse(path, filename="vi.srt", media_type="application/x-subrip")

@app.get("/api/jobs/{job_id}/download/voice")
def download_voiceover(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    path = job.files.get("voice_output")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Voiceover track has not been compiled yet.")
    return FileResponse(path, filename="voice_final.wav", media_type="audio/wav")

@app.get("/api/jobs/{job_id}/download/transcript")
def download_transcript(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    path = job.files.get("transcript_json")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Transcript data has not been generated yet.")
    return FileResponse(path, filename="transcript.json", media_type="application/json")


@app.get("/api/jobs/{job_id}/logs", response_class=PlainTextResponse)
def get_job_logs(job_id: str):
    log_path = job_store.get_job_logs_path(job_id)
    if not os.path.exists(log_path):
        raise HTTPException(status_code=404, detail="Logs file is not initialized.")
    with open(log_path, "r", encoding="utf-8") as f:
        return f.read()

@app.delete("/api/jobs/{job_id}", response_model=dict)
def delete_job_endpoint(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    
    if job.status == "processing":
        raise HTTPException(status_code=400, detail="Cannot delete a job that is currently processing.")
        
    deleted = job_store.delete_job(job_id)
    if not deleted:
        raise HTTPException(status_code=500, detail="Failed to delete job from storage.")
        
    return {"status": "success", "message": f"Job {job_id} deleted successfully."}

@app.post("/api/jobs/{job_id}/stop", response_model=JobInfo)
def stop_job_endpoint(job_id: str):
    job = job_store.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"Job with ID '{job_id}' not found.")
    
    if job.status != "processing":
        raise HTTPException(status_code=400, detail="Cannot stop a job that is not currently processing.")
        
    from app.pipeline.job_manager import cancel_job
    cancel_job(job_id)
    
    job = job_store.update_job(job_id, status="failed", error="Cancelled by user", step="failed")
    job_store.log_to_job(job_id, "Job cancellation requested by user.")
    return job


