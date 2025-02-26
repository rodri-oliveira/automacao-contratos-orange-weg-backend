from fastapi import APIRouter, HTTPException, UploadFile, File
from typing import List, Dict, Any
import os
import shutil
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

router = APIRouter()

# Diretório base para armazenar os arquivos
BASE_DIR = Path("data")

# Criar diretórios se não existirem
for folder in ["R189", "QPE", "SPB", "NFSERV"]:
    folder_path = BASE_DIR / folder
    folder_path.mkdir(parents=True, exist_ok=True)

@router.get("/{folder_type}/files", response_model=List[Dict[str, Any]])
async def list_files(folder_type: str) -> List[Dict[str, Any]]:
    """Lista arquivos em uma pasta específica."""
    try:
        folder_path = BASE_DIR / folder_type
        if not folder_path.exists():
            raise HTTPException(status_code=404, detail=f"Pasta {folder_type} não encontrada")
        
        files = []
        for file_path in folder_path.glob("*"):
            if file_path.is_file():
                files.append({
                    "name": file_path.name,
                    "status": "Disponível"
                })
        return files
    except Exception as e:
        logger.error(f"Erro ao listar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{folder_type}/upload")
async def upload_file(folder_type: str, file: UploadFile = File(...)):
    """Faz upload de um arquivo para uma pasta específica."""
    try:
        folder_path = BASE_DIR / folder_type
        if not folder_path.exists():
            raise HTTPException(status_code=404, detail=f"Pasta {folder_type} não encontrada")
        
        file_path = folder_path / file.filename
        with file_path.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        
        return {"message": f"Arquivo {file.filename} enviado com sucesso"}
    except Exception as e:
        logger.error(f"Erro ao fazer upload: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{folder_type}/process")
async def process_files(folder_type: str, file_names: List[str]):
    """Processa arquivos selecionados de uma pasta específica."""
    try:
        logger.info(f"Processando arquivos para {folder_type}: {file_names}")
        folder_path = BASE_DIR / folder_type
        if not folder_path.exists():
            raise HTTPException(status_code=404, detail=f"Pasta {folder_type} não encontrada")
        
        processed_files = []
        for file_name in file_names:
            file_path = folder_path / file_name
            if not file_path.exists():
                logger.warning(f"Arquivo não encontrado: {file_name}")
                processed_files.append({
                    "name": file_name,
                    "status": "Erro: Arquivo não encontrado"
                })
                continue
            
            try:
                # Aqui você pode adicionar a lógica de processamento específica
                # Por enquanto, só vamos simular que o arquivo foi processado
                logger.info(f"Processando arquivo: {file_name}")
                processed_files.append({
                    "name": file_name,
                    "status": "Processado com sucesso"
                })
            except Exception as e:
                logger.error(f"Erro ao processar arquivo {file_name}: {str(e)}")
                processed_files.append({
                    "name": file_name,
                    "status": f"Erro ao processar: {str(e)}"
                })
        
        return {"processed_files": processed_files}
    except Exception as e:
        logger.error(f"Erro ao processar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
