from fastapi import APIRouter, HTTPException, status, UploadFile, File
from typing import List, Dict, Any
from io import BytesIO
import logging
from pydantic import BaseModel

from app.core.sharepoint import SharePointClient
from app.core.extractors.r189_extractor import R189Extractor
from app.core.config import settings
from app.core.auth import SharePointAuth

router = APIRouter(prefix="/r189", tags=["R189"])
logger = logging.getLogger(__name__)

# Instâncias compartilhadas
sharepoint_client = SharePointClient()
r189_extractor = R189Extractor()

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
async def process_files(request: ProcessFilesRequest):
    """Processa arquivos R189 selecionados"""
    try:
        if not request.files:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Nenhum arquivo selecionado"
            )

        results = []
        for file_name in request.files:
            try:
                # Download do arquivo
                content = await sharepoint_client.download_file(
                    settings.R189_FOLDER, 
                    file_name
                )
                
                if not content:
                    results.append({
                        "file": file_name,
                        "status": "error",
                        "message": "Erro ao baixar arquivo"
                    })
                    continue

                # Processa o arquivo
                result = await r189_extractor.process_file(content)
                
                if not result["success"]:
                    results.append({
                        "file": file_name,
                        "status": "error",
                        "message": result["error"]
                    })
                    continue

                # Upload do arquivo consolidado
                if "consolidated_file" in result:
                    consolidated_name = f"Consolidado_{file_name.replace('.xlsb', '.xlsx')}"
                    success = await sharepoint_client.upload_file(
                        result["consolidated_file"],
                        consolidated_name,
                        settings.CONSOLIDATED_FOLDER
                    )

                    results.append({
                        "file": file_name,
                        "status": "success" if success else "error",
                        "message": ("Arquivo processado e consolidado com sucesso" 
                                  if success else "Erro ao enviar arquivo consolidado")
                    })
                else:
                    results.append({
                        "file": file_name,
                        "status": "error",
                        "message": "Arquivo processado mas sem conteúdo consolidado"
                    })

            except Exception as e:
                logger.error(f"Erro processando arquivo {file_name}: {str(e)}")
                results.append({
                    "file": file_name,
                    "status": "error",
                    "message": str(e)
                })

        return {
            "success": any(r["status"] == "success" for r in results),
            "results": results
        }

    except Exception as e:
        logger.error(f"Erro no processamento: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )

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
    logger.info(f"Recebida requisição para tipo: {tipo}")  # Add this log
    
    if tipo not in PASTAS:
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
        
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            logger.error("Falha ao obter token de autenticação")
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")

        # Mapear tipos de arquivo para suas extensões
        extensoes = {
            'R189': '.xlsb',
            'QPE': '.pdf',
            'SPB': '.pdf',
            'NFSERV': '.pdf',
            'MUN_CODE': '.xlsb'
        }

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
            logger.debug(f"Dados recebidos: {dados}")  # Log para debug
            arquivos = dados.get('d', {}).get('results', [])
            
            # Filtrar arquivos pela extensão correta
            extensao = extensoes.get(tipo, '')
            arquivos_filtrados = [
                {
                    "nome": arquivo["Name"],
                    "tamanho": arquivo["Length"],
                    "modificado": arquivo["TimeLastModified"]
                }
                for arquivo in arquivos
                if arquivo["Name"].lower().endswith(extensao)
            ]
            
            logger.info(f"Encontrados {len(arquivos_filtrados)} arquivos")
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

from fastapi import APIRouter, HTTPException
from app.core.auth import SharePointAuth
import logging
import json

router = APIRouter()
logger = logging.getLogger(__name__)

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
    logger.info(f"Recebida requisição para tipo: {tipo}")
    
    if tipo not in PASTAS:
        logger.warning(f"Tipo inválido recebido: {tipo}")
        raise HTTPException(status_code=400, detail="Tipo de arquivo inválido")
        
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            logger.error("Token não obtido")
            raise HTTPException(status_code=401, detail="Falha na autenticação")

        pasta = PASTAS[tipo]
        url = f"{auth.site_url}/_api/web/GetFolderByServerRelativeUrl('{pasta}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}"
        }
        
        logger.info(f"Fazendo requisição para: {url}")
        response = await auth.fazer_requisicao_sharepoint(url, headers)
        
        logger.debug(f"Resposta recebida - Status: {response.get('status_code')}")
        logger.debug(f"Resposta recebida - Texto: {response.get('text')}")
        
        if response.get('status_code') == 200:
            try:
                dados = json.loads(response.get('text'))
                logger.debug(f"Dados JSON parseados: {dados}")
                
                arquivos = dados.get('d', {}).get('results', [])
                logger.info(f"Encontrados {len(arquivos)} arquivos")
                
                return {
                    "success": True,
                    "arquivos": [
                        {
                            "nome": arquivo["Name"],
                            "tamanho": arquivo["Length"],
                            "modificado": arquivo["TimeLastModified"]
                        }
                        for arquivo in arquivos
                    ]
                }
            except json.JSONDecodeError as je:
                logger.error(f"Erro ao fazer parse do JSON: {str(je)}")
                raise HTTPException(status_code=500, detail="Erro ao processar resposta do SharePoint")
        
        logger.error(f"Erro na resposta do SharePoint: {response.get('status_code')}")
        raise HTTPException(
            status_code=response.get('status_code', 500),
            detail=f"Erro ao acessar SharePoint: {response.get('text')}"
        )
            
    except Exception as e:
        logger.error(f"Erro ao buscar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/api/processar/r189")
async def processar_arquivos(files: List[str]):
    """Processa os arquivos R189 selecionados."""
    try:
        extractor = R189Extractor()
        resultado = await extractor.process_selected_files(files)
        
        if resultado["success"]:
            return resultado
        else:
            raise HTTPException(
                status_code=400,
                detail=resultado["error"]
            )
            
    except Exception as e:
        logger.error(f"Erro ao processar arquivos: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=str(e)
        )