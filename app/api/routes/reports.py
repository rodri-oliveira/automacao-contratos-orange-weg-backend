from fastapi import APIRouter, UploadFile, File, Security, HTTPException
from app.core.security import TokenData, auth
from app.core.reports.divergence_report_nfserv_r189 import DivergenceReportNFSERVR189
from app.core.reports.divergence_report_qpe_r189 import DivergenceReportQPER189
from app.core.reports.divergence_report_spb_r189 import DivergenceReportSPBR189
from app.core.reports.report_mun_code_r189 import ReportMunCodeR189
from app.core.extractors.r189_extractor import R189Extractor
from app.core.extractors.qpe_extractor import QPEExtractor
from app.core.extractors.spb_extractor import SPBExtractor
from app.core.extractors.nfserv_extractor import NFServExtractor
from app.core.extractors.municipality_code_extractor import MunicipalityCodeExtractor
import pandas as pd
from typing import Dict, List, Any
from io import BytesIO

router = APIRouter()

@router.post("/divergence/nfserv-r189", response_model=Dict[str, Any])
async def check_nfserv_r189_divergences(
    nfserv_file: UploadFile = File(...),
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
):
    """Verifica divergências entre NFSERV e R189"""
    try:
        # Extrair dados dos arquivos
        nfserv_content = BytesIO(await nfserv_file.read())
        r189_content = BytesIO(await r189_file.read())
        
        # Processar arquivos
        nfserv_extractor = NFServExtractor()
        r189_extractor = R189Extractor()
        
        nfserv_result = await nfserv_extractor.extract(nfserv_content)
        r189_result = await r189_extractor.extract(r189_content)
        
        if not nfserv_result["success"]:
            raise HTTPException(status_code=400, detail=nfserv_result["error"])
        if not r189_result["success"]:
            raise HTTPException(status_code=400, detail=r189_result["error"])
        
        # Verificar divergências
        report = DivergenceReportNFSERVR189()
        result = await report.check_divergences(nfserv_result["data"], r189_result["data"])
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Gerar relatório Excel se houver divergências
        if result["divergences"]:
            excel_result = await report.generate_excel_report(result["divergences"])
            if excel_result["success"]:
                result["excel_report"] = excel_result
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivos: {str(e)}")

@router.post("/divergence/spb-r189", response_model=Dict[str, Any])
async def check_spb_r189_divergences(
    spb_file: UploadFile = File(...),
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
):
    """Verifica divergências entre SPB e R189"""
    try:
        # Extrair dados dos arquivos
        spb_content = BytesIO(await spb_file.read())
        r189_content = BytesIO(await r189_file.read())
        
        # Processar arquivos
        spb_extractor = SPBExtractor()
        r189_extractor = R189Extractor()
        
        spb_result = await spb_extractor.extract(spb_content)
        r189_result = await r189_extractor.extract(r189_content)
        
        if not spb_result["success"]:
            raise HTTPException(status_code=400, detail=spb_result["error"])
        if not r189_result["success"]:
            raise HTTPException(status_code=400, detail=r189_result["error"])
        
        # Verificar divergências
        report = DivergenceReportSPBR189()
        result = await report.check_divergences(spb_result["data"], r189_result["data"])
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Gerar relatório Excel se houver divergências
        if result["divergences"]:
            excel_result = await report.generate_excel_report(result["divergences"])
            if excel_result["success"]:
                result["excel_report"] = excel_result
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivos: {str(e)}")

@router.post("/divergence/qpe-r189", response_model=Dict[str, Any])
async def check_qpe_r189_divergences(
    qpe_file: UploadFile = File(...),
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
):
    """Verifica divergências entre QPE e R189"""
    try:
        # Extrair dados dos arquivos
        qpe_content = BytesIO(await qpe_file.read())
        r189_content = BytesIO(await r189_file.read())
        
        # Processar arquivos
        qpe_extractor = QPEExtractor()
        r189_extractor = R189Extractor()
        
        qpe_result = await qpe_extractor.extract(qpe_content)
        r189_result = await r189_extractor.extract(r189_content)
        
        if not qpe_result["success"]:
            raise HTTPException(status_code=400, detail=qpe_result["error"])
        if not r189_result["success"]:
            raise HTTPException(status_code=400, detail=r189_result["error"])
        
        # Verificar divergências
        report = DivergenceReportQPER189()
        result = await report.check_divergences(qpe_result["data"], r189_result["data"])
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Gerar relatório Excel se houver divergências
        if result["divergences"]:
            excel_result = await report.generate_excel_report(result["divergences"])
            if excel_result["success"]:
                result["excel_report"] = excel_result
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivos: {str(e)}")

@router.post("/municipality-codes", response_model=Dict[str, Any])
async def check_municipality_codes(
    r189_file: UploadFile = File(...),
    municipality_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
):
    """Verifica códigos de município no R189"""
    try:
        # Extrair dados dos arquivos
        r189_content = BytesIO(await r189_file.read())
        municipality_content = BytesIO(await municipality_file.read())
        
        # Processar arquivos
        r189_extractor = R189Extractor()
        municipality_extractor = MunicipalityCodeExtractor()
        
        r189_result = await r189_extractor.extract(r189_content)
        municipality_result = await municipality_extractor.extract(municipality_content)
        
        if not r189_result["success"]:
            raise HTTPException(status_code=400, detail=r189_result["error"])
        if not municipality_result["success"]:
            raise HTTPException(status_code=400, detail=municipality_result["error"])
        
        # Verificar códigos de município
        report = ReportMunCodeR189()
        result = await report.check_municipality_codes(r189_result["data"], municipality_result["data"])
        
        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["error"])
        
        # Gerar relatório Excel se houver divergências
        if result["divergences"]:
            excel_result = await report.generate_excel_report(
                result["divergences"],
                municipality_result["data"]
            )
            if excel_result["success"]:
                result["excel_report"] = excel_result
        
        return result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar arquivos: {str(e)}")