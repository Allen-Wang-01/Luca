# Confirms the API key was loaded from .env without ever printing its value.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import settings

key = settings.openai_api_key
print("key loaded:", bool(key))
print("key length:", len(key) if key else 0)
print("base_url:", settings.openai_base_url or "(default: https://api.openai.com/v1)")
