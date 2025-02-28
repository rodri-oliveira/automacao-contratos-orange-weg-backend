from fastapi import APIRouter, HTTPException
from app.core.auth import SharePointAuth
from app.core.extractors.qpe_extractor import QPEExtractor
import logging

router = APIRouter()
logger = logging.getLogger(__name__)

PASTAS = {
    'QPE': "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
}

@router.get("/api/arquivos/{tipo}")
async def buscar_arquivos(tipo: str):
    """Busca arquivos QPE no SharePoint."""
    logger.info(f"Iniciando busca de arquivos do tipo: {tipo}")
    
    if tipo not in PASTAS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
        
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            logger.error("Falha ao obter token de autenticação")
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")

        pasta = PASTAS[tipo]
        url = f"{auth.site_url}/_api/web/GetFolderByServerRelativeUrl('{pasta}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"Fazendo requisição para: {url}")
        response = await auth.fazer_requisicao_sharepoint(url, headers)
        
        if response.status_code == 200:
            dados = response.json()
            logger.debug(f"Resposta completa: {dados}")
            arquivos = dados.get('d', {}).get('results', [])
            
            # Filtra apenas arquivos PDF
            arquivos_filtrados = [
                {
                    "nome": arquivo["Name"],
                    "tamanho": arquivo["Length"],
                    "modificado": arquivo["TimeLastModified"]
                }
                for arquivo in arquivos
                if arquivo["Name"].lower().endswith('.pdf')
            ]
            
            logger.info(f"Encontrados {len(arquivos_filtrados)} arquivos PDF")
            
            return {
                "success": True,
                "arquivos": arquivos_filtrados
            }
            
        logger.error(f"Erro na resposta do SharePoint: {response.status_code}")
        logger.error(f"Resposta: {response.text}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Erro ao acessar SharePoint: {response.text}"
        )
            
    except Exception as e:
        logger.error(f"Erro ao buscar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))