import os

from dotenv import load_dotenv

from autodub.core.paths import app_data_dir, bin_dir, cache_dir, logs_dir, package_root, project_root, runtime_data_dir, storage_dir

BASE_DIR = str(package_root())
PROJECT_ROOT = str(project_root())
APP_DATA_DIR = str(app_data_dir())

load_dotenv(dotenv_path=os.path.join(PROJECT_ROOT, ".env"), override=True)
load_dotenv(dotenv_path=os.path.join(APP_DATA_DIR, ".env"), override=True)

RUNTIME_DATA_DIR = str(runtime_data_dir())
STORAGE_DIR = str(storage_dir())
CACHE_DIR = str(cache_dir())
LOGS_DIR = str(logs_dir())
MODELS_DIR = os.path.join(RUNTIME_DATA_DIR, "models")

PORT = int(os.getenv("PORT", 8000))
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


def _resolve_data_path(value: str) -> str:
    return value if os.path.isabs(value) else os.path.abspath(os.path.join(PROJECT_ROOT, value))


OLLAMA_MODELS_DIR = _resolve_data_path(os.getenv("OLLAMA_MODELS_DIR", os.path.join(MODELS_DIR, "ollama")))
HF_HOME = _resolve_data_path(os.getenv("HF_HOME", os.path.join(CACHE_DIR, "huggingface")))
TORCH_HOME = _resolve_data_path(os.getenv("TORCH_HOME", os.path.join(CACHE_DIR, "torch")))
os.environ["OLLAMA_MODELS_DIR"] = OLLAMA_MODELS_DIR
os.environ["HF_HOME"] = HF_HOME
os.environ["TORCH_HOME"] = TORCH_HOME

for directory in (RUNTIME_DATA_DIR, STORAGE_DIR, CACHE_DIR, LOGS_DIR, MODELS_DIR, OLLAMA_MODELS_DIR, HF_HOME, TORCH_HOME):
    os.makedirs(directory, exist_ok=True)

JOBS_DIR = STORAGE_DIR
