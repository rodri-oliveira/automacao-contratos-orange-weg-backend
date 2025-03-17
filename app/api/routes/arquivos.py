from fastapi import APIRouter, HTTPException
from app.core.auth import SharePointAuth
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/{tipo}")
async def list_files(tipo: str):
    """
    Lista os arquivos do tipo especificado disponíveis no SharePoint
    """
    try:
        logger.info(f"Listando arquivos {tipo}")
        
        # Mapeia o tipo para o caminho no SharePoint
        caminhos = {
            "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
            "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
            "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
            "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
            "MUN_CODE": "/teams/BR-TI-TIN/AutomaoFinanas/MUN_CODE"
        }
        
        if tipo.upper() not in caminhos:
            logger.error(f"Tipo de arquivo inválido: {tipo}")
            raise HTTPException(status_code=400, detail=f"Tipo de arquivo inválido: {tipo}")
        
        sharepoint_auth = SharePointAuth()
        arquivos = await sharepoint_auth.listar_arquivos_sharepoint(caminhos[tipo.upper()])
        
        if arquivos:
            logger.info(f"Encontrados {len(arquivos)} arquivos do tipo {tipo}")
            return {
                "success": True,
                "arquivos": arquivos
            }
        else:
            logger.warning(f"Nenhum arquivo encontrado para o tipo {tipo}")
            return {
                "success": True,  # Mudamos para True para evitar erro no frontend
                "arquivos": []    # Retornamos uma lista vazia em vez de erro
            }
    except Exception as e:
        logger.error(f"Erro ao listar arquivos {tipo}: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Erro ao listar arquivos: {str(e)}") 