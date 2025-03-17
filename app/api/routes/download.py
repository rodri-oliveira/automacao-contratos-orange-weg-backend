from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
import os
from app.core.auth import SharePointAuth

router = APIRouter()

@router.get("/report/{filename}")
async def download_report(filename: str):
    """
    Permite o download de um relatório específico.
    """
    try:
        # Caminho da pasta de relatórios
        relatorios_path = "/teams/BR-TI-TIN/AutomaoFinanas/RELATÓRIOS"
        
        # Baixa o arquivo do SharePoint
        sharepoint_auth = SharePointAuth()
        file_content = sharepoint_auth.baixar_arquivo_sharepoint(
            filename,
            relatorios_path
        )
        
        if file_content is None:
            raise HTTPException(status_code=404, detail="Arquivo não encontrado")
        
        # Salva temporariamente o arquivo
        temp_path = f"/tmp/{filename}"
        with open(temp_path, "wb") as f:
            f.write(file_content)
        
        # Retorna o arquivo para download
        return FileResponse(
            path=temp_path,
            filename=filename,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao baixar arquivo: {str(e)}") 