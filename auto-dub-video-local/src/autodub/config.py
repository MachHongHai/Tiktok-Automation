from dotenv import load_dotenv
import os

from autodub.core.paths import app_data_dir, bin_dir, cache_dir, logs_dir, package_root, project_root, storage_dir

BASE_DIR = str(package_root())
PROJECT_ROOT = str(project_root())
APP_DATA_DIR = str(app_data_dir())
LOGS_DIR = str(logs_dir())
CACHE_DIR = str(cache_dir())

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"))
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
LEGACY_OLLAMA_MODELS_DIR = os.path.join(PROJECT_ROOT, ".cache", "ollama_models")
OLLAMA_MODELS_DIR_RAW = os.getenv(
    "OLLAMA_MODELS_DIR",
    LEGACY_OLLAMA_MODELS_DIR if os.path.exists(LEGACY_OLLAMA_MODELS_DIR) else os.path.join(CACHE_DIR, "ollama", "models"),
)
OLLAMA_MODELS_DIR = (
    OLLAMA_MODELS_DIR_RAW
    if os.path.isabs(OLLAMA_MODELS_DIR_RAW)
    else os.path.abspath(os.path.join(PROJECT_ROOT, OLLAMA_MODELS_DIR_RAW))
)

# Create base directories
os.makedirs(APP_DATA_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(OLLAMA_MODELS_DIR, exist_ok=True)
JOBS_DIR = os.path.join(STORAGE_DIR, "jobs")
os.makedirs(JOBS_DIR, exist_ok=True)

