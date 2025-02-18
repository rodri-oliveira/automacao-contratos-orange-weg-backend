from fastapi import FastAPI
from app.core.config import settings

from app.api.main import api_router
from app.api.routes import health

app = FastAPI(
    title="automacao_financas_backend",
    version="0.0.1",
    docs_url="/api",
)

if settings.root_path is not None:
    app.root_path = settings.root_path

if settings.swagger_servers_list is not None:
    app.servers = list(map(lambda x: { "url": x }, settings.swagger_servers_list.split(",")))

app.include_router(api_router, prefix="/api")
app.include_router(health.router, prefix="/health")