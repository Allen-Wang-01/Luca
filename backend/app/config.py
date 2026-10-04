from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    openai_api_key: str | None = None
    openai_base_url: str | None = None
    # Local development only: a directory of saved runs (`{name}.json` parsed report +
    # `{name}.narration.json` from scripts/narrate_sample.py) the frontend can load via
    # /api/dev/samples/{name} to preview the UI without any API calls. Unset (the
    # default) leaves that endpoint unregistered entirely.
    dev_samples_dir: str | None = None

    @field_validator("openai_api_key", "openai_base_url", "dev_samples_dir", mode="before")
    @classmethod
    def _blank_string_to_none(cls, value: object) -> object:
        # A blank line in .env (e.g. "OPENAI_BASE_URL=") loads as "" rather than
        # unset - without this, that "" gets passed straight to the OpenAI SDK as an
        # explicit base_url override, breaking request URL construction entirely.
        if isinstance(value, str) and value.strip() == "":
            return None
        return value


settings = Settings()
