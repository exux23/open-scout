from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="SCOUT_", env_file=".env", extra="ignore")

    data_dir: Path = Path("data")
    api_key: str = ""
    neural: bool = False
    model: str = "BAAI/bge-small-en-v1.5"
    api_url: str = "http://127.0.0.1:8000"
