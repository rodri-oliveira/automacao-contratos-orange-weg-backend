from fastapi import APIRouter, HTTPException, status
from typing import List
import logging
import traceback

from app.core.extractors.municipality_code_extractor import MunicipalityCodeExtractor

router = APIRouter(prefix="/mun_code", tags=["MUN_CODE"])
logger = logging.getLogger(__name__)

@router.post("/process")
async def process_mun_code_files(files: List[str]):
    """Processa os arquivos Municipality Code selecionados."""
    logger.info("=== INICIANDO PROCESSAMENTO DE ARQUIVOS MUNICIPALITY CODE ===")
    logger.info(f"Arquivos recebidos: {files}")
    
    try:
        if not files:
            logger.error("Nenhum arquivo selecionado")
            return {"success": False, "error": "Nenhum arquivo selecionado"}
            
        logger.info("Criando instância do MunicipalityCodeExtractor")
        mun_code_extractor = MunicipalityCodeExtractor()
        
        logger.info("Chamando process_selected_files")
        result = await mun_code_extractor.process_selected_files(files)
        logger.info(f"Resultado do processamento: {result}")
        
        return result
            
    except Exception as e:
        logger.error(f"Erro ao processar arquivos Municipality Code: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}