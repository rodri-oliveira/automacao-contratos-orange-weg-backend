from fastapi import APIRouter, HTTPException
import logging
import traceback
from typing import Dict, Any

from app.core.reports.report_mun_code_r189 import ReportMunCodeR189
from app.core.reports.divergence_report_qpe_r189 import DivergenceReportQPER189
from app.core.reports.divergence_report_spb_r189 import DivergenceReportSPBR189
from app.core.reports.divergence_report_nfserv_r189 import DivergenceReportNFSERVR189
from app.core.reports.divergence_report_r189 import DivergenceReportR189

router = APIRouter()
logger = logging.getLogger(__name__)

@router.post("/mun_code_r189")
async def validate_mun_code_r189():
    """
    Executa a validação entre MUN_CODE e R189
    """
    try:
        logger.info("=== INICIANDO VALIDAÇÃO MUN_CODE vs R189 ===")
        validator = ReportMunCodeR189()
        
        # Adicionar await aqui para obter o resultado real
        result = await validator.generate_report()
        logger.info(f"Resultado da validação: {result}")
        
        return result
    except Exception as e:
        logger.error(f"Erro na validação MUN_CODE vs R189: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        }

@router.post("/r189")
async def validate_r189():
    """
    Valida os dados do R189 e gera relatório de divergências.
    """
    logger.info("=== INICIANDO VALIDAÇÃO R189 ===")
    try:
        validator = DivergenceReportR189()
        result = await validator.generate_report()
        
        if result["success"]:
            logger.info(f"Validação R189 concluída com sucesso: {result.get('message')}")
            return {"success": True, "message": result.get("message")}
        else:
            logger.error(f"Erro na validação R189: {result.get('error')}")
            return {"success": False, "error": result.get("error")}
    except Exception as e:
        logger.exception(f"Erro na validação R189: {str(e)}")
        return {"success": False, "error": f"Erro na validação R189: {str(e)}"}

@router.post("/qpe_r189", response_model=Dict[str, Any])
async def validate_qpe_r189():
    """
    Valida divergências entre QPE e R189.
    """
    try:
        logger.info("Iniciando validação QPE vs R189")
        validator = DivergenceReportQPER189()
        
        result = await validator.generate_report()
        
        logger.info(f"Validação QPE vs R189 concluída: {result}")
        return result
    except Exception as e:
        logger.exception(f"Erro na validação QPE vs R189: {str(e)}")
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}",
            "show_popup": True
        }

@router.post("/spb_r189")
async def validate_spb_r189():
    """
    Executa a validação entre SPB e R189
    """
    try:
        logger.info("=== INICIANDO VALIDAÇÃO SPB vs R189 ===")
        validator = DivergenceReportSPBR189()
        result = await validator.check_divergences()
        
        if result["success"] and result.get("divergences"):
            report_result = await validator.generate_excel_report(result["divergences"])
            return report_result
        
        return result
    except Exception as e:
        logger.error(f"Erro na validação SPB vs R189: {str(e)}")
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
        logger.info("=== INICIANDO VALIDAÇÃO NFSERV vs R189 ===")
        validator = DivergenceReportNFSERVR189()
        result = await validator.check_divergences()
        
        if result["success"] and result.get("divergences"):
            report_result = await validator.generate_excel_report(result["divergences"])
            return report_result
        
        return result
    except Exception as e:
        logger.error(f"Erro na validação NFSERV vs R189: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "success": False,
            "error": f"Erro na validação: {str(e)}"
        }