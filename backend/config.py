import json
from pathlib import Path

CONFIG_DIR = Path.home() / ".config" / "ink-boss"
CONFIG_FILE = CONFIG_DIR / "config.json"
SESSIONS_DIR = CONFIG_DIR / "sessions"
CONFIG_DIR.mkdir(parents=True, exist_ok=True)
SESSIONS_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_CONFIG = {
    "version": "2.0.0",
    "theme": "dark",
    "llm": {
        "backend": "ollama",
        "ollamaUrl": "http://localhost:11434",
        "ollamaModel": "llama3",
        "claudeApiKey": "",
        "geminiApiKey": "",
    },
    "hibernate_minutes": 10,
    "services": [],
    "groups": [],
}

def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_CONFIG.copy()

def save_config(config: dict):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
