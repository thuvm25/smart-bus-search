from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    es_host: str = "http://localhost:9200"
    es_index: str = "bus_waypoints"

    model_config = SettingsConfigDict(env_file=".env", case_sensitive=False)


settings = Settings()
