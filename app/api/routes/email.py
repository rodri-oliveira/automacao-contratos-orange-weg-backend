from fastapi import APIRouter, Query
import logging
import traceback
from typing import Optional

from app.core.extractors.email_extractor import EmailExtractor

router = APIRouter(prefix="/email", tags=["Email"])
logger = logging.getLogger(__name__)

@router.post("/process")
async def process_emails(days_limit: Optional[int] = Query(7, description="Número de dias para buscar emails")):
    """
    Processa emails da pasta 'Contratos de TI' e move os anexos para o SharePoint.
    """
    try:
        logger.info(f"Iniciando processamento de emails dos últimos {days_limit} dias")
        
        email_extractor = EmailExtractor()
        result = await email_extractor.process_emails(days_limit)
        
        logger.info(f"Processamento de emails concluído: {result}")
        return result
        
    except Exception as e:
        logger.error(f"Erro ao processar emails: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro ao processar emails: {str(e)}",
            "show_popup": True
        } 