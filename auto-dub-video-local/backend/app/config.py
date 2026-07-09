from dotenv import load_dotenv
import os

from app.core.paths import app_data_dir, backend_dir, bin_dir, cache_dir, logs_dir, storage_dir

BASE_DIR = str(backend_dir())
APP_DATA_DIR = str(app_data_dir())
LOGS_DIR = str(logs_dir())
CACHE_DIR = str(cache_dir())

load_dotenv(dotenv_path=os.path.join(BASE_DIR, ".env"))
load_dotenv(dotenv_path=os.path.join(APP_DATA_DIR, ".env"))

PORT = int(os.getenv("PORT", 8000))
STORAGE_DIR = str(storage_dir())

BIN_DIR = str(bin_dir())
if os.path.exists(BIN_DIR):
    os.environ["PATH"] = BIN_DIR + os.path.pathsep + os.environ["PATH"]

WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")
TRANSLATOR_PROVIDER = os.getenv("TRANSLATOR_PROVIDER", "mock")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-3.5-turbo")

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2:7b")
OLLAMA_MODELS_DIR = os.getenv("OLLAMA_MODELS_DIR", os.path.join(CACHE_DIR, "ollama", "models"))

# Create base directories
os.makedirs(APP_DATA_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OLLAMA_MODELS_DIR, exist_ok=True)
JOBS_DIR = os.path.join(STORAGE_DIR, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)
