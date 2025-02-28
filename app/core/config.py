from pydantic_settings import BaseSettings
from dotenv import load_dotenv
import os

load_dotenv()

class Settings(BaseSettings):
    # Configurações do SharePoint
    SITE_URL: str = os.getenv("SITE_URL", "")
    CLIENT_ID: str = os.getenv("CLIENT_ID", "")
    CLIENT_SECRET: str = os.getenv("CLIENT_SECRET", "")
    TENANT_ID: str = os.getenv("TENANT_ID", "")
    RESOURCE: str = os.getenv("RESOURCE", "")

    # Caminhos das pastas no SharePoint
    R189_FOLDER: str = "/teams/BR-TI-TIN/AutomaoFinanas/R189"
    CONSOLIDATED_FOLDER: str = "/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO"

    # Configurações da API
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "Automação Finanças API"

    class Config:
        case_sensitive = True

settings = Settings()