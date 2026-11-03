"""Application configuration via environment variables."""
from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file="../.env", env_file_encoding="utf-8", extra="ignore")

    database_url: str = "sqlite:///./aurora.db"
    demo_user_id: str = "00000000-0000-0000-0000-000000000001"

    # AI provider: "mock" or "watsonx"
    ai_provider: str = "mock"
    watsonx_api_key: str = ""
    watsonx_project_id: str = ""
    watsonx_url: str = "https://us-south.ml.cloud.ibm.com"
    watsonx_model_id: str = "ibm/granite-13b-chat-v2"

    # Weather provider: "sample" or "openweathermap"
    weather_provider: str = "sample"
    openweathermap_api_key: str = ""
    weather_location: str = "Stony Brook, NY, US"

    # CORS — allow local Vite dev server
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]


settings = Settings()
