from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import r189, qpe, spb, nfserv, municipality_code, validation

app = FastAPI(
    title="Automação Finanças API",
    description="API para automação de processos financeiros",
    version="1.0.0"
)

# Configurar CORS primeiro - Ajustando para permitir todas as origens para teste
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Temporariamente permitir todas as origens
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Depois adicionar as rotas
app.include_router(r189.router)
app.include_router(qpe.router)
app.include_router(spb.router)
app.include_router(nfserv.router)
app.include_router(municipality_code.router)
app.include_router(validation.router, prefix="/api/validations", tags=["Validations"])