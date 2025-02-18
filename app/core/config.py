from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    root_path: Optional[str] = None
    swagger_servers_list: Optional[str] = None
    jwt_issuer: str
    jwt_audience: str
    class Config:
        env_file = ".env"

settings = Settings()  # type: ignore