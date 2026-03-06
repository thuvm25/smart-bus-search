from pydantic import AnyHttpUrl
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from environment variables or .env file
    """

    # Elasticsearch
    es_host: AnyHttpUrl = "http://elasticsearch:9200"
    es_index_bus_waypoints: str = "bus_waypoints"

    # API
    api_prefix: str = "/api"

    # CORS
    cors_allow_origins: list[str] = ["*"]

    # Environment config
    model_config = SettingsConfigDict(
        env_prefix="BUSGPS_",   # ENV variables must start with BUSGPS_
        env_file=".env",        # load from .env automatically
        case_sensitive=False
    )


settings = Settings()