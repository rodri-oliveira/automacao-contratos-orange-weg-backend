from fastapi import APIRouter, HTTPException
from app.core.reports.divergence_report_qpe_r189 import DivergenceReportQPER189
from app.core.reports.divergence_report_spb_r189 import DivergenceReportSPBR189
from app.core.reports.divergence_report_nfserv_r189 import DivergenceReportNFSERVR189
from app.core.reports.report_mun_code_r189 import ReportMunCodeR189
from app.core.reports.divergence_report_r189 import DivergenceReportR189
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/qpe_r189")
async def validate_qpe_r189():
    """
    Executa a validação entre QPE e R189
    """
    try:
        logger.info("Iniciando validação QPE x R189")
        # Implementar a lógica de validação QPE x R189
        return {
            "success": True,
            "message": "Validação QPE x R189 não implementada ainda"
        }
    except Exception as e:
        logger.error(f"Erro na validação QPE x R189: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        }

@router.post("/spb_r189")
async def validate_spb_r189():
    """
    Executa a validação entre SPB e R189
    """
    try:
        logger.info("Iniciando validação SPB x R189")
        # Implementar a lógica de validação SPB x R189
        return {
            "success": True,
            "message": "Validação SPB x R189 não implementada ainda"
        }
    except Exception as e:
        logger.error(f"Erro na validação SPB x R189: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        }

@router.post("/nfserv_r189")
async def validate_nfserv_r189():
    """
    Executa a validação entre NFSERV e R189
    """
    try:
        logger.info("Iniciando validação NFSERV x R189")
        # Implementar a lógica de validação NFSERV x R189
        return {
            "success": True,
            "message": "Validação NFSERV x R189 não implementada ainda"
        }
    except Exception as e:
        logger.error(f"Erro na validação NFSERV x R189: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        }

@router.post("/mun_code_r189")
async def validate_mun_code_r189():
    """
    Executa a validação entre MUN_CODE e R189
    """
    try:
        logger.info("Iniciando validação MUN_CODE vs R189")
        
        # Inicializar o validador
        validator = ReportMunCodeR189()
        
        # Chamar o método generate_report que faz todo o processo
        result = await validator.generate_report()
        
        return result
        
    except Exception as e:
        logger.error(f"Erro na validação MUN_CODE vs R189: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        }

@router.post("/r189")
async def validate_r189():
    """
    Executa a validação do R189
    """
    try:
        logger.info("Iniciando validação R189")
        
        # Inicializar o validador
        validator = DivergenceReportR189()
        
        # Chamar o método generate_report que faz todo o processo
        result = await validator.generate_report()
        
        return result
        
    except Exception as e:
        logger.error(f"Erro na validação R189: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        } 