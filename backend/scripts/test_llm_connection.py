# Minimal isolated call to the OpenAI Responses API - no PDF, no structured output,
# no gatekeeper. Used to tell apart "connectivity/auth/model-name problem" from
# "something specific to our parsing pipeline" when debugging /api/reports/parse.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI

from app.config import settings

client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

response = client.responses.create(model="gpt-5.6-luna", input="Reply with OK.")
print(response.output_text)
