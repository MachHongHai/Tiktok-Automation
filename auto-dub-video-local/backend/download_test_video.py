import os
import urllib.request

# Find project root directory (parent of backend)
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEST_DIR = os.path.join(BASE_DIR, "test")
os.makedirs(TEST_DIR, exist_ok=True)

# Add local bin folder (containing ffmpeg/ffprobe) to PATH so yt-dlp can use it for range cutting
ffmpeg_bin = os.path.join(BASE_DIR, 'backend', 'bin')
if os.path.exists(ffmpeg_bin):
    os.environ["PATH"] = ffmpeg_bin + os.path.pathsep + os.environ["PATH"]

dest_path = os.path.join(TEST_DIR, "english_sample.mp4")

# YouTube video URL: Steve Jobs Stanford Commencement Speech (Official Stanford Upload)
# The first 30 seconds contains: "I am honored to be with you today for your commencement..."
youtube_url = "https://www.youtube.com/watch?v=D1R-jKKp3NA"

print(f"Downloading test video from YouTube: {youtube_url}")

success = False
try:
    # Import yt-dlp programmatically
    import yt_dlp
    
    # Configure options
    # We download format 18 (360p mp4 video with aac audio) or best, and cut the first 30 seconds
    ydl_opts = {
        'format': 'best[ext=mp4]/best',
        'outtmpl': os.path.join(TEST_DIR, 'english_sample_raw.%(ext)s'),
        'overwrites': True,
        'download_ranges': lambda info_dict, self: [{'start_time': 0, 'end_time': 30}],
        'force_keyframes_at_cuts': True,
        'quiet': False
    }
    
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        ydl.download([youtube_url])
        
    # Check if download succeeded and rename to final name
    raw_path_mp4 = os.path.join(TEST_DIR, "english_sample_raw.mp4")
    if os.path.exists(raw_path_mp4):
        if os.path.exists(dest_path):
            os.remove(dest_path)
        os.rename(raw_path_mp4, dest_path)
        print(f"Successfully downloaded and saved: {dest_path}")
        success = True
    else:
        # Search for any english_sample_raw.* files
        for f in os.listdir(TEST_DIR):
            if f.startswith("english_sample_raw."):
                raw_path = os.path.join(TEST_DIR, f)
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(raw_path, dest_path)
                print(f"Successfully downloaded and renamed {f} to: {dest_path}")
                success = True
                break
except Exception as e:
    print(f"YouTube download failed: {e}")

if not success:
    # Fallback to direct URL if yt-dlp fails
    fallback_url = "https://github.com/Artemso/BTTLR_hackathon/raw/main/speech.mp4"
    print(f"Trying fallback download from: {fallback_url}")
    try:
        req = urllib.request.Request(
            fallback_url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req, timeout=15) as response:
            if response.status == 200:
                with open(dest_path, 'wb') as out_file:
                    out_file.write(response.read())
                print(f"Successfully downloaded fallback video and saved to: {dest_path}")
                success = True
    except Exception as fe:
        print(f"Fallback failed: {fe}")

if not success:
    print("Error: Failed to fetch any test video.")
