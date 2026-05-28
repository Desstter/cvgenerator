from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    ai_provider: str = "claude"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    claude_model: str = "claude-sonnet-4-20250514"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-2.5-flash"
    gemini_fallback_models: list[str] = [
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    ]

    # Token limits per model
    claude_max_tokens: int = 16384
    openai_max_tokens: int = 4096
    gemini_max_tokens: int = 8192

    max_upload_size_mb: int = 10
    default_template: str = "modern"

    base_dir: Path = Path(__file__).resolve().parent.parent
    uploads_dir: Path = base_dir / "uploads"
    outputs_dir: Path = base_dir / "outputs"
    saved_dir: Path = base_dir / "saved"
    templates_dir: Path = base_dir / "app" / "templates"
    static_dir: Path = base_dir / "app" / "static"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
settings.uploads_dir.mkdir(exist_ok=True)
settings.outputs_dir.mkdir(exist_ok=True)
settings.saved_dir.mkdir(exist_ok=True)
