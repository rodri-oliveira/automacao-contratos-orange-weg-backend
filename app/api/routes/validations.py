from fastapi import APIRouter, HTTPException, Security, UploadFile, File
from typing import Dict, Any, List
from app.core.security import TokenData, auth
from application.reports.divergence_report_r189 import DivergenceReportR189
from application.reports.divergence_report_qpe_r189 import DivergenceReportQPER189
from application.reports.divergence_report_spb_r189 import DivergenceReportSPBR189
from application.reports.divergence_report_nfserv_r189 import DivergenceReportNFSERVR189
from application.reports.report_mun_code_r189 import DivergenceReportMUNCODER189
import pandas as pd

router = APIRouter()

@router.post("/r189", response_model=Dict[str, Any])
async def validate_r189(
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
) -> Dict[str, Any]:
    """Validate R189 file for divergences."""
    try:
        r189_df = pd.read_excel(r189_file.file)
        report = DivergenceReportR189()
        success, message, divergences = report.check_divergences(r189_df)
        
        return {
            "success": success,
            "message": message,
            "divergences": divergences.to_dict('records') if success and not divergences.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/qpe-r189", response_model=Dict[str, Any])
async def validate_qpe_r189(
    qpe_file: UploadFile = File(...),
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
) -> Dict[str, Any]:
    """Validate QPE against R189 for divergences."""
    try:
        qpe_df = pd.read_excel(qpe_file.file)
        r189_df = pd.read_excel(r189_file.file)
        
        report = DivergenceReportQPER189()
        success, message, divergences = report.check_divergences(qpe_df, r189_df)
        
        return {
            "success": success,
            "message": message,
            "divergences": divergences.to_dict('records') if success and not divergences.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/spb-r189", response_model=Dict[str, Any])
async def validate_spb_r189(
    spb_file: UploadFile = File(...),
    r189_file: UploadFile = File(...),
    nfserv_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
) -> Dict[str, Any]:
    """Validate SPB against R189 for divergences."""
    try:
        spb_df = pd.read_excel(spb_file.file)
        r189_df = pd.read_excel(r189_file.file)
        nfserv_df = pd.read_excel(nfserv_file.file)
        
        report = DivergenceReportSPBR189()
        success, message, divergences = report.check_divergences(spb_df, r189_df, nfserv_df)
        
        return {
            "success": success,
            "message": message,
            "divergences": divergences.to_dict('records') if success and not divergences.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/nfserv-r189", response_model=Dict[str, Any])
async def validate_nfserv_r189(
    nfserv_file: UploadFile = File(...),
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
) -> Dict[str, Any]:
    """Validate NFSERV against R189 for divergences."""
    try:
        nfserv_df = pd.read_excel(nfserv_file.file)
        r189_df = pd.read_excel(r189_file.file)
        
        report = DivergenceReportNFSERVR189()
        success, message, divergences = report.check_divergences(nfserv_df, r189_df)
        
        return {
            "success": success,
            "message": message,
            "divergences": divergences.to_dict('records') if success and not divergences.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/mun-code-r189", response_model=Dict[str, Any])
async def validate_mun_code_r189(
    r189_file: UploadFile = File(...),
    token: TokenData = Security(auth.verify)
) -> Dict[str, Any]:
    """Validate municipality codes in R189 file."""
    try:
        r189_df = pd.read_excel(r189_file.file)
        
        report = DivergenceReportMUNCODER189()
        success, message, divergences = report.check_divergences(r189_df)
        
        return {
            "success": success,
            "message": message,
            "divergences": divergences.to_dict('records') if success and not divergences.empty else []
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))