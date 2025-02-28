from fastapi import APIRouter, HTTPException, status
from app.core.auth import SharePointAuth
from app.core.extractors.nfserv_extractor import NFSERVExtractor
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/api/arquivos/{tipo}")
async def buscar_arquivos(tipo: str):
    """Busca arquivos NFSERV no SharePoint."""
    if tipo != "NFSERV":
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
        
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")

        pasta = "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV"
        url = f"{auth.site_url}/_api/web/GetFolderByServerRelativeUrl('{pasta}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"Fazendo requisição para: {url}")
        response = await auth.fazer_requisicao_sharepoint(url, headers)
        
        if response.status_code == 200:
            dados = response.json()
            arquivos = dados.get('d', {}).get('results', [])
            
            return {
                "success": True,
                "arquivos": [
                    {
                        "nome": arquivo["Name"],
                        "tamanho": arquivo["Length"],
                        "modificado": arquivo["TimeLastModified"]
                    }
                    for arquivo in arquivos
                    if arquivo["Name"].lower().endswith('.pdf')  # NFSERV usa arquivos PDF
                ]
            }
            
        logger.error(f"Erro na resposta do SharePoint: {response.status_code}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Erro ao acessar SharePoint: {response.text}"
        )
            
    except Exception as e:
        logger.error(f"Erro ao buscar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))