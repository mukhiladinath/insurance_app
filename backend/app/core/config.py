"""
config.py — Application configuration.

All settings are loaded from environment variables (or the .env file).
Never hardcode secrets in source files.
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # -------------------------------------------------------------------------
    # App
    # -------------------------------------------------------------------------
    app_env: str = Field(default="development", alias="APP_ENV")
    api_prefix: str = Field(default="/api", alias="API_PREFIX")

    # -------------------------------------------------------------------------
    # MongoDB
    # -------------------------------------------------------------------------
    mongo_uri: str = Field(..., alias="MONGO_URI")
    mongo_db_name: str = Field(default="insurance_app", alias="MONGO_DB_NAME")

    # -------------------------------------------------------------------------
    # Azure OpenAI — primary LLM (finobi-4o-mini deployment)
    # -------------------------------------------------------------------------
    azure_oai_endpoint: str = Field(..., alias="AZURE_OAI_ENDPOINT")
    azure_oai_api_key: str = Field(..., alias="AZURE_OAI_API_KEY")
    azure_oai_api_version: str = Field(default="2024-08-01-preview", alias="AZURE_OAI_API_VERSION")
    azure_deployment_name: str = Field(
        default="finobi-4o-mini", alias="AZURE_finobi4omini_DEPLOYMENT_NAME"
    )

    # -------------------------------------------------------------------------
    # Google Gemini (secondary / document processing)
    # -------------------------------------------------------------------------
    gemini_api_key: str | None = Field(default=None, alias="GEMINI_API_KEY")
    gemini_model_name: str = Field(
        default="gemini-2.5-pro", alias="GEMINI_PRO25_MODEL_NAME"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"  # ignore unknown env vars (plenty in .env)
        populate_by_name = True


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached application settings."""
    return Settings()
