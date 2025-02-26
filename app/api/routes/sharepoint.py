from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from app.core.sharepoint import SharePointClient
from app.core.extractors.r189_extractor import R189Extractor
import logging

# Configurando logging
logger = logging.getLogger(__name__)

router = APIRouter()
sharepoint = SharePointClient()

@router.get("/{folder_type}/files", response_model=List[Dict[str, Any]])
async def list_files(folder_type: str) -> List[Dict[str, Any]]:
    """Lista arquivos em uma pasta específica do SharePoint."""
    try:
        if folder_type not in sharepoint.folders:
            raise HTTPException(status_code=400, detail=f"Tipo de pasta inválido: {folder_type}")
        
        files = await sharepoint.list_files(sharepoint.folders[folder_type])
        if not files:
            logger.warning(f"Nenhum arquivo encontrado na pasta {folder_type}")
            return []
            
        return files
    except Exception as e:
        logger.error(f"Erro ao listar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/{folder_type}/process")
async def process_files(folder_type: str, file_names: List[str]) -> Dict[str, Any]:
    """Processa arquivos selecionados de uma pasta específica."""
    try:
        if folder_type not in sharepoint.folders:
            raise HTTPException(status_code=400, detail=f"Tipo de pasta inválido: {folder_type}")
        
        folder_path = sharepoint.folders[folder_type]
        processed_files = []
        
        for file_name in file_names:
            try:
                # Baixa o arquivo do SharePoint
                file_content = await sharepoint.download_file(folder_path, file_name)
                if not file_content:
                    processed_files.append({
                        "name": file_name,
                        "status": "Erro: Arquivo não encontrado no SharePoint"
                    })
                    continue
                
                # Processa o arquivo de acordo com o tipo
                if folder_type == 'R189':
                    extractor = R189Extractor()
                    result = await extractor.extract(file_content)
                    if result["success"]:
                        # Consolida o arquivo R189
                        await extractor.consolidar_r189(file_content)
                        processed_files.append({
                            "name": file_name,
                            "status": "Processado com sucesso",
                            "data": result["data"]
                        })
                    else:
                        processed_files.append({
                            "name": file_name,
                            "status": f"Erro: {result['error']}"
                        })
                else:
                    # TODO: Implementar outros tipos (QPE, SPB, etc.)
                    processed_files.append({
                        "name": file_name,
                        "status": "Tipo de arquivo não implementado"
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