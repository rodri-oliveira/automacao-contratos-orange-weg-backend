from fastapi import APIRouter, HTTPException
import logging
from app.core.report_consolidator import ReportConsolidator

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["Reports"])

@router.post("/consolidate")
async def consolidate_reports():
    """
    Consolida os relatórios mais recentes de cada tipo em um único arquivo.
    """
    try:
        consolidator = ReportConsolidator()
        result = await consolidator.consolidate_reports()
        
        if result and result.get('success'):
            return {
                'success': True,
                'message': "Relatórios consolidados com sucesso",
                'filename': result.get('filename'),
                'path': result.get('path'),
                'reports_included': result.get('reports_included', [])
            }
        else:
            error_msg = result.get('error', "Falha na consolidação dos relatórios")
            return {
                'success': False,
                'error': error_msg
            }
    except Exception as e:
        logger.error(f"Erro ao consolidar relatórios: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/latest")
async def get_latest_reports():
    """
    Retorna a lista dos relatórios mais recentes disponíveis para cada tipo.
    """
    try:
        consolidator = ReportConsolidator()
        latest_reports = {}
        
        for report_type in consolidator.report_paths.keys():
            report = await consolidator._get_latest_report(report_type)
            if report:
                latest_reports[report_type] = {
                    'name': report['name'],
                    'path': report['path']
                }
        
        return {
            'success': True,
            'latest_reports': latest_reports
        }
    except Exception as e:
        logger.error(f"Erro ao listar relatórios mais recentes: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e)) 