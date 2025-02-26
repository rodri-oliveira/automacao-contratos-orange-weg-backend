from fastapi import FastAPI, APIRouter, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import os
import requests
from dotenv import load_dotenv
import sys

# Adicionar o caminho do diretório automacao-contratos-fincancas ao sys.path
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'automacao-contratos-fincancas'))

# Agora podemos importar o SharePointAuth
from auth.auth import SharePointAuth

app = FastAPI()

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Carregar variáveis de ambiente
load_dotenv()

# Constantes
SITE_URL = os.getenv('SITE_URL')
PASTAS = {
    'R189': "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    'QPE': "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    'SPB': "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
    'NFSERV': "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    'MUN_CODE': "/teams/BR-TI-TIN/AutomaoFinanas/R189"  # Usa a mesma pasta do R189
}

api_router = APIRouter()

@api_router.get("/arquivos/{tipo}")
async def buscar_arquivos(tipo: str):
    """
    Busca arquivos no SharePoint para o tipo especificado (R189, QPE, etc).
    """
    if tipo not in PASTAS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
        
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")

        pasta = PASTAS[tipo]
        url = f"{SITE_URL}/_api/web/GetFolderByServerRelativeUrl('{pasta}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        response = requests.get(url, headers=headers)
        
        if response.status_code == 200:
            dados = response.json()
            arquivos = [
                {
                    "nome": arquivo["Name"],
                    "tamanho": arquivo["Length"],
                    "modificado": arquivo["TimeLastModified"]
                }
                for arquivo in dados["d"]["results"]
            ]
            return {"arquivos": arquivos}
        else:
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Erro ao buscar arquivos: {response.status_code}"
            )
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/processar/{tipo}")
async def processar_arquivos(tipo: str, arquivos: list[str]):
    """
    Processa os arquivos selecionados do tipo especificado.
    """
    # TODO: Implementar processamento dos arquivos
    pass

@app.get("/")
async def root():
    return {"message": "API da Automação de Contratos - Finanças"}

app.include_router(api_router, prefix="/api", tags=["API"])

from app.api.routes import items, reports, sharepoint, files

app.include_router(sharepoint.router, prefix="/sharepoint", tags=["SharePoint"])
app.include_router(reports.router, prefix="/reports", tags=["Reports"])
app.include_router(items.router, prefix="/items", tags=["Items"])
app.include_router(files.router, prefix="/files", tags=["Files"])
