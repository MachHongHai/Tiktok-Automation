import os
from dotenv import load_dotenv

# Load environmental variables from .env file
load_dotenv(dotenv_path=os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

PORT = int(os.getenv("PORT", 8000))
STORAGE_DIR = os.getenv("STORAGE_DIR", "../storage")

# Resolve to absolute path
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Append local bin folder to PATH for portable FFmpeg support
BIN_DIR = os.path.join(BASE_DIR, "bin")
if os.path.exists(BIN_DIR):
    os.environ["PATH"] = BIN_DIR + os.path.pathsep + os.environ["PATH"]

if not os.path.isabs(STORAGE_DIR):

    STORAGE_DIR = os.path.abspath(os.path.join(BASE_DIR, STORAGE_DIR))

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
TRANSLATOR_PROVIDER = os.getenv("TRANSLATOR_PROVIDER", "mock")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")

# Create base directories
os.makedirs(STORAGE_DIR, exist_ok=True)
JOBS_DIR = os.path.join(STORAGE_DIR, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)
