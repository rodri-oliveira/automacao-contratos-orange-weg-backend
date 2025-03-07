from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.routes import r189, qpe, spb, nfserv, municipality_code, validation

app = FastAPI(
    title="Automação Finanças API",
    description="API para automação de processos financeiros",
    version="1.0.0"
)

# Configurar CORS primeiro
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)

# Depois adicionar as rotas
app.include_router(r189.router, prefix="/api/r189", tags=["R189"])
app.include_router(qpe.router, prefix="/api/qpe", tags=["QPE"])
app.include_router(spb.router, prefix="/api/spb", tags=["SPB"])
app.include_router(nfserv.router, prefix="/api/nfserv", tags=["NFSERV"])
app.include_router(municipality_code.router, prefix="/api/municipality_code", tags=["Municipality Code"])
app.include_router(validation.router, prefix="/api/validation", tags=["Validation"])

@app.get("/")
async def root():
    return {"message": "Automação Finanças API"}