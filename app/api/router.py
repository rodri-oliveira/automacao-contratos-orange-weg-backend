from fastapi import APIRouter, HTTPException
import os
import requests
from dotenv import load_dotenv
import logging
from typing import List
from io import BytesIO

from app.core.sharepoint import SharePointClient  # Mantenha SharePointClient
from app.core.extractors.r189_extractor import R189Extractor

# Configurar logger
logger = logging.getLogger(__name__)

# Criar o router
api_router = APIRouter()

# Carregar variáveis de ambiente
load_dotenv()

# Constantes
SITE_URL = os.getenv('SITE_URL')
PASTAS = {
    'R189': '/teams/BR-TI-TIN/AutomaoFinanas/R189',
    'CONSOLIDADO': '/teams/BR-TI-TIN/AutomaoFinanas/CONSOLIDADO'
}

@api_router.get("/arquivos/{tipo}")
async def buscar_arquivos(tipo: str):
    """Busca arquivos na pasta especificada do SharePoint."""
    logger.info(f"Buscando arquivos do tipo: {tipo}")
    
    if tipo not in PASTAS:
        raise HTTPException(status_code=400, detail=f"Tipo de arquivo inválido: {tipo}")
            
    try:
        sharepoint_client = SharePointClient()
        token = sharepoint_client.auth.acquire_token()
        
        if not token:
            logger.error("Falha ao obter token do SharePoint")
            raise HTTPException(status_code=401, detail="Falha na autenticação com SharePoint")

        # Construir URL corretamente
        folder_path = PASTAS[tipo]
        url = f"{os.getenv('SITE_URL')}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files"
        
        headers = {
            "Accept": "application/json;odata=verbose",
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }
        
        logger.debug(f"Fazendo requisição para: {url}")
        response = requests.get(url, headers=headers)
        logger.debug(f"Status code da resposta: {response.status_code}")
        
        if response.status_code == 200:
            dados = response.json()
            arquivos = [
                {
                    "nome": arquivo["Name"],
                    "tamanho": arquivo["Length"],
                    "modificado": arquivo["TimeLastModified"]
                }
                for arquivo in dados["d"]["results"]
            ]
            return {"arquivos": arquivos}
        else:
            logger.error(f"Erro na resposta do SharePoint: {response.text}")
            raise HTTPException(
                status_code=response.status_code,
                detail=f"Erro ao buscar arquivos: {response.text}"
            )
            
    except Exception as e:
        logger.error(f"Erro ao buscar arquivos: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.post("/api/processar/R189")
async def processar_r189(arquivos: List[str]):
    logger.info(f"Iniciando processamento de arquivos R189: {arquivos}")
    try:
        auth = SharePointAuth()
        sharepoint_client = SharePointClient()
        extractor = R189Extractor()
        
        resultados = []
        for arquivo in arquivos:
            logger.info(f"Processando arquivo: {arquivo}")
            try:
                # Log do caminho completo
                caminho_completo = f"{PASTAS['R189']}/{arquivo}"
                logger.info(f"Tentando baixar arquivo do caminho: {caminho_completo}")

                # Baixar arquivo do SharePoint
                conteudo = await sharepoint_client.download_file(
                    folder_path=PASTAS['R189'],
                    file_name=arquivo
                )
                
                if not conteudo:
                    logger.error(f"Erro ao baixar arquivo {arquivo}")
                    resultados.append({
                        "arquivo": arquivo,
                        "status": "erro",
                        "mensagem": f"Erro ao baixar arquivo: {arquivo}"
                    })
                    continue

                # Processar arquivo
                resultado = await extractor.process_file(BytesIO(conteudo))
                
                if resultado["success"]:
                    # Nome do arquivo consolidado
                    nome_consolidado = f"R189_consolidado_{arquivo.replace('.xlsb', '.xlsx')}"
                    
                    # Upload do arquivo consolidado
                    upload_success = await sharepoint_client.upload_file(
                        file_content=resultado["consolidated_file"],
                        destination_name=nome_consolidado,
                        folder_path=PASTAS['CONSOLIDADO']
                    )
                    
                    if upload_success:
                        resultados.append({
                            "arquivo": arquivo,
                            "status": "sucesso",
                            "mensagem": "Arquivo processado e consolidado com sucesso"
                        })
                    else:
                        resultados.append({
                            "arquivo": arquivo,
                            "status": "erro",
                            "mensagem": "Erro ao enviar arquivo consolidado"
                        })
                else:
                    resultados.append({
                        "arquivo": arquivo,
                        "status": "erro",
                        "mensagem": resultado.get("error", "Erro ao consolidar arquivo")
                    })

            except Exception as e:
                logger.error(f"Erro ao processar arquivo {arquivo}: {str(e)}")
                resultados.append({
                    "arquivo": arquivo,
                    "status": "erro",
                    "mensagem": str(e)
                })

        return {
            "status": "success",
            "message": "Processamento concluído",
            "processados": resultados
        }

    except Exception as e:
        logger.error(f"Erro no processamento R189: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

# Incluir rotas
api_router.include_router(r189.router, prefix="/r189", tags=["R189"])
api_router.include_router(sharepoint.router, prefix="/sharepoint", tags=["SharePoint"])
api_router.include_router(reports.router, prefix="/reports", tags=["Reports"])
api_router.include_router(items.router, prefix="/items", tags=["Items"])
api_router.include_router(files.router, prefix="/files", tags=["Files"])
