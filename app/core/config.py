from pydantic_settings import BaseSettings
from typing import Optional

class Settings(BaseSettings):
    root_path: Optional[str] = None
    swagger_servers_list: Optional[str] = None
    jwt_issuer: str = "automacao-financas-api"
    jwt_audience: str = "automacao-financas-client"
    client_id: str = "your_client_id"
    client_secret: str = "your_client_secret"
    tenant_id: str = "your_tenant_id"
    resource: str = "your_resource"
    site_url: str = "your_sharepoint_site_url"

    class Config:
        env_file = ".env"

settings = Settings()  # type: ignore