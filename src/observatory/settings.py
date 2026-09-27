from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")
    observatory_host: str = "127.0.0.1"
    observatory_port: int = Field(8765, ge=1024, le=65535)
    observatory_db: Path = Path("data/observatory.db")
    observatory_export: bool = False
    observatory_project_url: str = ""
    observatory_max_runs: int = Field(2, ge=1, le=4)
    logfire_token: SecretStr | None = None
    logfire_base_url: str = "https://logfire-us.pydantic.dev"
