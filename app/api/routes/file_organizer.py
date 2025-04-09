from fastapi import APIRouter, HTTPException, Query
from typing import Dict, List, Optional
import logging
import re
from app.core.sharepoint import SharePointClient
import os

router = APIRouter()
logger = logging.getLogger(__name__)

# Constantes para os caminhos base
PATHS = {
    "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",
    "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
    "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV"
}

# Padrões de arquivo para cada tipo
FILE_PATTERNS = {
    "R189": r"^1\.\s*R189\s+WEG",
    "QPE": r"QPE-\d{6}(?![a-zA-Z])",
    "SPB": r"SPB-\d{6}(?![a-zA-Z])",
    "NFSERV": r".*(?:QPE_SPB|BLU|POA|VIX|SPB|REC|BHO|QPE-\d{6}R).*"
}

@router.post("/organize-files")
async def organize_files(
    source_folder: Optional[str] = Query(None, description="Nome da pasta de origem dentro de ENTRADA"),
    destination_folder: str = Query(..., description="Nome da pasta de destino a ser criada nas pastas alvo")
):
    """
    Organiza os arquivos da pasta ENTRADA para suas respectivas pastas destino.
    
    O usuário pode especificar:
    - source_folder: Subpasta dentro de ENTRADA (opcional). Se não informado, usa a raiz de ENTRADA.
    - destination_folder: Nome da pasta de destino que será criada nas pastas alvo (ex: "2025-03").
    """
    try:
        sharepoint_client = SharePointClient()
        
        # Determinar o caminho completo de origem
        entrada_path = PATHS["ENTRADA"]
        if source_folder:
            entrada_path = f"{entrada_path}/{source_folder}"
            
        logger.info(f"Pasta de origem: {entrada_path}")
        logger.info(f"Pasta de destino a ser criada: {destination_folder}")
        
        # Verificar se a pasta de entrada existe
        entrada_files = await sharepoint_client.list_files(entrada_path)
        if entrada_files is None:
            return {"message": f"A pasta {entrada_path} não existe ou não foi possível acessá-la"}
            
        if not entrada_files:
            return {"message": f"Nenhum arquivo encontrado na pasta {entrada_path}"}
            
        # Garantir que as pastas de destino existam
        for path_type in ["R189", "QPE", "SPB", "NFSERV"]:
            destination_path = f"{PATHS[path_type]}/{destination_folder}"
            await ensure_folder_exists(sharepoint_client, PATHS[path_type], destination_folder)

        results = []
        for file in entrada_files:
            file_name = file.get("Name", "")
            destination_type = None
            
            # Log para debug
            logger.info(f"Analisando arquivo: {file_name}")

            # Identificar o tipo do arquivo
            for file_type, pattern in FILE_PATTERNS.items():
                if re.search(pattern, file_name, re.IGNORECASE):
                    destination_type = file_type
                    logger.info(f"Arquivo {file_name} corresponde ao padrão {file_type}")
                    break

            if destination_type:
                # Construir caminho destino
                destination_path = f"{PATHS[destination_type]}/{destination_folder}"
                logger.info(f"Movendo arquivo {file_name} para {destination_path}")
                
                # Tentar mover o arquivo
                success = await move_file(
                    sharepoint_client,
                    file_name,
                    entrada_path,
                    destination_path
                )

                results.append({
                    "file_name": file_name,
                    "destination_type": destination_type,
                    "destination_path": destination_path,
                    "success": success
                })
            else:
                logger.warning(f"Arquivo {file_name} não corresponde a nenhum padrão conhecido")
                results.append({
                    "file_name": file_name,
                    "destination_type": None,
                    "destination_path": None,
                    "success": False,
                    "reason": "Não corresponde a nenhum padrão conhecido"
                })

        return {
            "message": "Processamento concluído",
            "source_folder": entrada_path,
            "destination_folder": destination_folder,
            "processed_count": len(results),
            "success_count": sum(1 for r in results if r["success"]),
            "results": results
        }

    except Exception as e:
        logger.error(f"Erro ao organizar arquivos: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao organizar arquivos: {str(e)}"
        )

async def move_file(client: SharePointClient, file_name: str, source_path: str, destination_path: str) -> bool:
    """
    Move um arquivo de uma pasta para outra no SharePoint.
    1. Faz o download do arquivo da origem
    2. Faz o upload para o destino
    """
    try:
        # Download do arquivo
        file_content = await client.download_file(source_path, file_name)
        if not file_content:
            logger.error(f"Não foi possível baixar o arquivo {file_name} de {source_path}")
            return False

        # Upload para o destino
        success = await client.upload_file(
            file_content,
            file_name,
            destination_path
        )
        
        if success:
            logger.info(f"Arquivo {file_name} movido com sucesso para {destination_path}")
        else:
            logger.error(f"Falha ao fazer upload do arquivo {file_name} para {destination_path}")
            
        return success

    except Exception as e:
        logger.error(f"Erro ao mover arquivo {file_name}: {str(e)}")
        return False

async def ensure_folder_exists(client: SharePointClient, parent_path: str, folder_name: str) -> bool:
    """
    Verifica se uma pasta existe no SharePoint e a cria se não existir.
    
    Args:
        client: Cliente SharePoint
        parent_path: Caminho da pasta pai
        folder_name: Nome da pasta a verificar/criar
        
    Returns:
        bool: True se a pasta existe ou foi criada com sucesso, False caso contrário
    """
    try:
        # Caminho completo da pasta
        folder_path = f"{parent_path}/{folder_name}"
        
        # Tentar listar arquivos na pasta para verificar se ela existe
        files = await client.list_files(folder_path)
        
        # Se conseguir listar (mesmo que vazio), a pasta existe
        if files is not None:
            logger.info(f"Pasta {folder_path} já existe")
            return True
        
        # Se não conseguir listar, tentar criar a pasta
        logger.info(f"Pasta {folder_path} não existe. Tentando criar...")
        success = await client.create_folder(parent_path, folder_name)
        
        if success:
            logger.info(f"Pasta {folder_path} criada com sucesso")
            return True
        else:
            logger.error(f"Falha ao criar pasta {folder_path}")
            return False
            
    except Exception as e:
        logger.error(f"Erro ao verificar/criar pasta {parent_path}/{folder_name}: {str(e)}")
        return False 