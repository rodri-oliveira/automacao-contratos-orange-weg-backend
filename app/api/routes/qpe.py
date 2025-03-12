from fastapi import APIRouter, HTTPException, status, UploadFile, File, Body, Request
from typing import List, Dict, Any
from io import BytesIO
import logging
from pydantic import BaseModel
import traceback
import json

from app.core.sharepoint import SharePointClient
from app.core.extractors.r189_extractor import R189Extractor
from app.core.config import settings
from app.core.auth import SharePointAuth
from app.core.extractors.qpe_extractor import QPEExtractor

router = APIRouter(prefix="/qpe", tags=["QPE"])
logger = logging.getLogger(__name__)

# Instâncias compartilhadas
sharepoint_client = SharePointClient()
qpe_extractor = QPEExtractor()

class ProcessFilesRequest(BaseModel):
    files: List[str]

@router.get("/files")
async def list_r189_files():
    """Lista os arquivos R189 disponíveis no SharePoint"""
    try:
        sharepoint = SharePointClient()
        pasta_r189 = '/teams/BR-TI-TIN/AutomaoFinanas/R189'
        
        files = await sharepoint.list_files(pasta_r189)
        
        if files is None:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Erro ao listar arquivos"
            )
        
        # Filtra apenas arquivos .xlsb
        r189_files = [
            {
                "name": file["Name"],
                "size": file["Length"],
                "modified": file["TimeLastModified"]
            }
            for file in files
            if file["Name"].lower().endswith('.xlsb')
        ]
        
        return {
            "success": True,
            "files": r189_files
        }
        
    except Exception as e:
        logger.error(f"Erro ao listar arquivos R189: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.post("/process")
async def process_qpe_files(files: List[str]):
    """Processa os arquivos QPE selecionados."""
    logger.info("=== INICIANDO PROCESSAMENTO DE ARQUIVOS QPE ===")
    logger.info(f"Arquivos recebidos: {files}")
    
    try:
        if not files:
            logger.error("Nenhum arquivo selecionado")
            return {"success": False, "error": "Nenhum arquivo selecionado"}
            
        logger.info("Criando instância do QPEExtractor")
        qpe_extractor = QPEExtractor()
        
        logger.info("Chamando process_selected_files")
        result = await qpe_extractor.process_selected_files(files)
        logger.info(f"Resultado do processamento: {result}")
        
        return result
            
    except Exception as e:
        logger.error(f"Erro ao processar arquivos QPE: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

@router.get("/verify/{file_name}")
async def verify_file(file_name: str):
    """Verifica se um arquivo consolidado existe"""
    try:
        consolidated_name = f"Consolidado_{file_name.replace('.xlsb', '.xlsx')}"
        
        exists = await sharepoint_client.check_file_exists(
            settings.CONSOLIDATED_FOLDER,
            consolidated_name
        )
        
        return {
            "success": True,
            "exists": exists,
            "file": consolidated_name,
            "folder": settings.CONSOLIDATED_FOLDER
        }
    except Exception as e:
        logger.error(f"Erro ao verificar arquivo: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

@router.get("/download/{file_name}")
async def download_file(file_name: str):
    """Download de um arquivo R189 consolidado"""
    try:
        content = await sharepoint_client.download_file(
            settings.CONSOLIDATED_FOLDER,
            file_name
        )
        
        if not content:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Arquivo {file_name} não encontrado"
            )
        
        return {
            "success": True,
            "content": content,
            "file_name": file_name
        }
        
    except HTTPException as he:
        raise he
    except Exception as e:
        logger.error(f"Erro ao fazer download: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

PASTAS = {
    'R189': "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    'QPE': "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    'SPB': "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
    'NFSERV': "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    'MUN_CODE': "/teams/BR-TI-TIN/AutomaoFinanas/R189"
}

@router.get("/api/arquivos/{tipo}")
async def buscar_arquivos(tipo: str):
    """Busca arquivos no SharePoint."""
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
        url = f"{settings.SITE_URL}/_api/web/GetFolderByServerRelativeUrl('{pasta}')/Files"
        
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
                    if arquivo["Name"].lower().endswith('.xlsb')
                ]
            }
            
        logger.error(f"Erro na resposta do SharePoint: {response.status_code} - {response.text}")
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Erro ao acessar SharePoint: {response.text}"
        )
            
    except Exception as e:
        logger.error(f"Erro ao buscar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/test")
async def test_qpe_route(files: List[str]):
    """Rota de teste para verificar a recepção de dados."""
    return {
        "success": True,
        "received_files": files,
        "count": len(files)
    }