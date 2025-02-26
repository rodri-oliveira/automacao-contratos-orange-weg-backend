from fastapi import APIRouter, UploadFile, File, HTTPException, status
from typing import List, Dict, Any
from io import BytesIO
from app.core.sharepoint import SharePointClient
from app.core.config import settings
from app.core.services.processing_service import ProcessingService
import pandas as pd

router = APIRouter()
sharepoint_client = SharePointClient()
processing_service = ProcessingService()

@router.post("/upload")
async def upload_files(
    files: List[UploadFile] = File(...)
) -> Dict[str, Any]:
    """Handle file uploads and store them in SharePoint."""
    try:
        uploaded_files = []
        for file in files:
            content = await file.read()
            file_content = BytesIO(content)
            
            # Upload to SharePoint
            await sharepoint_client.upload_file(
                file_content=file_content,
                destination_name=file.filename,
                folder_path=settings.sharepoint_upload_folder
            )
            
            uploaded_files.append({
                "name": file.filename,
                "size": len(content),
                "status": "success"
            })
            
        return {"files": uploaded_files}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro durante upload do arquivo: {str(e)}"
        )

@router.post("/process")
async def process_files(
    files: Dict[str, List[str]]
) -> Dict[str, Any]:
    """Process uploaded files and generate divergence report."""
    try:
        # Download files from SharePoint
        file_contents = {}
        for file_type, file_names in files.items():
            for file_name in file_names:
                content = await sharepoint_client.download_file(
                    folder_path=settings.sharepoint_upload_folder,
                    file_name=file_name
                )
                file_contents[file_type] = BytesIO(content)

        # Process files
        result = await processing_service.process_files(file_contents)
        
        if not result["success"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=result["error"]
            )

        return {
            "success": True,
            "divergences": result["divergences"]
        }

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro durante processamento: {str(e)}"
        )

@router.get("/download-report")
async def download_report(
    report_data: Dict[str, Any]
) -> Dict[str, Any]:
    """Generate and download Excel report from results."""
    try:
        # Convert divergences to DataFrame
        df = pd.DataFrame(report_data["divergences"])
        
        # Create Excel file in memory
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        
        output.seek(0)
        
        return {
            "success": True,
            "file_content": output,
            "filename": f"relatorio_divergencias_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Erro ao gerar relatório: {str(e)}"
        )