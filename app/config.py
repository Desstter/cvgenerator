from pydantic_settings import BaseSettings
from pathlib import Path


class Settings(BaseSettings):
    ai_provider: str = "claude"

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_api_key: str = ""

    claude_model: str = "claude-sonnet-5"
    openai_model: str = "gpt-4o"
    gemini_model: str = "gemini-3.5-flash"
    gemini_fallback_models: list[str] = [
        "gemini-2.5-flash",
        "gemini-3.1-flash-lite",
    ]

    # Token limits per model
    claude_max_tokens: int = 16384
    openai_max_tokens: int = 4096
    # Generous budget: on gemini-2.5 models "thinking" tokens count against
    # max_output_tokens, and a truncated response silently degrades the CV
    # (json-repair recovers partial JSON and drops fields).
    gemini_max_tokens: int = 32768

    max_upload_size_mb: int = 10
    default_template: str = "modern"

    # Second AI pass that critiques and rewrites the weakest bullets/summary.
    # Doubles API usage per adaptation; disable if hitting rate limits.
    refine_pass: bool = True

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
