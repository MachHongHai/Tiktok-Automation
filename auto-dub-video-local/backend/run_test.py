import os
import time
import requests

BACKEND_URL = "http://127.0.0.1:8000"
VIDEO_PATH = r"d:\Du-an\Tiktok Automation\auto-dub-video-local\test\english_sample.mp4"

def test_pipeline():
    if not os.path.exists(VIDEO_PATH):
        print(f"Error: Test video not found at {VIDEO_PATH}")
        return

    print("Step 1: Uploading video and creating job...")
    with open(VIDEO_PATH, "rb") as f:
        files = {"video": ("english_sample.mp4", f, "video/mp4")}
        data = {
            "mode": "A",
            "source_language": "auto",
            "target_language": "vi",
            "tts_voice": "vi-VN-NamMinhNeural",
            "output_format": "keep_ratio",
            "font_size": 14,
            "margin_bottom": 40,
            "outline": 2,
            "max_chars_per_line": 32
        }
        response = requests.post(f"{BACKEND_URL}/api/jobs", files=files, data=data)
        
    if response.status_code != 200:
        print(f"Failed to create job: {response.text}")
        return
        
    job_info = response.json()
    job_id = job_info["job_id"]
    print(f"Job created successfully. ID: {job_id}")
    
    print("\nStep 2: Triggering job processing...")
    proc_response = requests.post(f"{BACKEND_URL}/api/jobs/{job_id}/process")
    if proc_response.status_code != 200:
        print(f"Failed to start processing: {proc_response.text}")
        return
        
    print("Processing started. Polling logs...")
    
    last_log_len = 0
    while True:
        status_resp = requests.get(f"{BACKEND_URL}/api/jobs/{job_id}")
        if status_resp.status_code != 200:
            print(f"Failed to fetch job status: {status_resp.text}")
            break
            
        status_info = status_resp.json()
        status = status_info["status"]
        step = status_info["step"]
        progress = status_info["progress"]
        
        # Get and display new logs
        logs_resp = requests.get(f"{BACKEND_URL}/api/jobs/{job_id}/logs")
        if logs_resp.status_code == 200:
            log_content = logs_resp.text
            if len(log_content) > last_log_len:
                new_logs = log_content[last_log_len:]
                import sys
                try:
                    sys.stdout.buffer.write(new_logs.encode('utf-8', errors='ignore'))
                    sys.stdout.flush()
                except Exception:
                    print(new_logs.encode('ascii', errors='ignore').decode('ascii'), end="", flush=True)
                last_log_len = len(log_content)
                
        if status in ["done", "failed"]:
            print(f"\nJob ended with status: {status}")
            if status == "done":
                print("Final files generated:")
                for k, v in status_info.get("files", {}).items():
                    print(f" - {k}: {v}")
            else:
                print(f"Error: {status_info.get('error')}")
            break
            
        time.sleep(2)

if __name__ == "__main__":
    test_pipeline()
