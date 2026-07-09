import os
import urllib.request
import zipfile

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN_DIR = os.path.join(BASE_DIR, "runtime", "bin")
os.makedirs(BIN_DIR, exist_ok=True)

FFMPEG_URL = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffmpeg-4.4.1-win-64.zip"
FFPROBE_URL = "https://github.com/ffbinaries/ffbinaries-prebuilt/releases/download/v4.4.1/ffprobe-4.4.1-win-64.zip"

def download_and_extract(url, name):
    zip_path = os.path.join(BIN_DIR, f"{name}.zip")
    print(f"Downloading {name} from {url}...")
    try:
        # User-agent header to prevent download blocks
        req = urllib.request.Request(
            url, 
            headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        )
        with urllib.request.urlopen(req) as response, open(zip_path, 'wb') as out_file:
            out_file.write(response.read())
            
        print(f"Extracting {name}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(BIN_DIR)
        os.remove(zip_path)
        print(f"Successfully set up {name}.")
    except Exception as e:
        print(f"Failed to download/extract {name}: {e}")

if __name__ == "__main__":
    download_and_extract(FFMPEG_URL, "ffmpeg")
    download_and_extract(FFPROBE_URL, "ffprobe")
    print("Local bin directory populated successfully.")
