import os
import re
import logging
import traceback
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from io import BytesIO

from app.core.auth import SharePointAuth

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/files-repository",
    tags=["files-repository"],
    responses={404: {"description": "Not found"}},
)

# Caminhos das pastas de origem
PATHS = {
    "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",
    "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
}

# Caminhos das pastas de destino (repositório)
REPOSITORY_PATHS = {
    "CADASTRAR": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar",
    "ESCRITURAR": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Escriturar",
    "NOTA_FISCAL": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Nota_Fiscal_Serviço"
}

async def get_token_and_site_url():
    """Obtém o token e a URL do site SharePoint."""
    try:
        logger.info("[REPOSITORY] Obtendo token de autenticação e URL do site")
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token")
            raise Exception("Falha ao obter token de autenticação")
            
        logger.info(f"[REPOSITORY] Token obtido com sucesso. Site URL: {site_url}")
        return token, site_url
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao obter token e URL: {str(e)}")
        logger.error(traceback.format_exc())
        raise

async def list_files(token, site_url, folder_path, limit=1000):
    """Lista os arquivos em uma pasta do SharePoint."""
    try:
        logger.info(f"[REPOSITORY] Listando arquivos da pasta: {folder_path}")
        
        url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files?$top={limit}"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }
        
        response = await make_request("GET", url, headers=headers)
        
        if response.status_code == 200:
            data = response.json()
            files = data.get("d", {}).get("results", [])
            
            logger.info(f"[REPOSITORY] {len(files)} arquivos encontrados na pasta {folder_path}")
            return files
        else:
            logger.error(f"[REPOSITORY] Erro ao listar arquivos: {response.status_code}")
            logger.error(f"[REPOSITORY] Resposta: {response.text}")
            return []
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao listar arquivos: {str(e)}")
        logger.error(traceback.format_exc())
        return []

async def download_file(token, site_url, folder_path, file_name):
    """Faz download de um arquivo do SharePoint."""
    try:
        logger.info(f"[REPOSITORY] Baixando arquivo: {folder_path}/{file_name}")
        
        download_url = f"{site_url}/_api/web/GetFileByServerRelativeUrl('{folder_path}/{file_name}')/$value"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }
        
        response = await make_request("GET", download_url, headers=headers)
        
        if response.status_code == 200:
            logger.info(f"[REPOSITORY] Arquivo baixado com sucesso: {file_name}")
            return response.content
        else:
            logger.error(f"[REPOSITORY] Erro ao baixar arquivo: {response.status_code}")
            logger.error(f"[REPOSITORY] Resposta: {response.text}")
            return None
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao baixar arquivo: {str(e)}")
        logger.error(traceback.format_exc())
        return None

async def upload_file(token, site_url, file_content, file_name, folder_path):
    """Faz upload de um arquivo para o SharePoint."""
    try:
        logger.info(f"[REPOSITORY] Fazendo upload de arquivo: {folder_path}/{file_name}")
        
        upload_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(url='{file_name}',overwrite=true)"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream"
        }
        
        response = await make_request("POST", upload_url, headers=headers, data=file_content)
        
        if response.status_code in [200, 201]:
            logger.info(f"[REPOSITORY] Upload concluído com sucesso: {file_name}")
            return True
        else:
            logger.error(f"[REPOSITORY] Erro ao fazer upload: {response.status_code}")
            logger.error(f"[REPOSITORY] Resposta: {response.text}")
            return False
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao fazer upload: {str(e)}")
        logger.error(traceback.format_exc())
        return False

async def check_folder_exists(token, site_url, folder_path):
    """Verifica se uma pasta existe no SharePoint."""
    try:
        logger.info(f"[REPOSITORY] Verificando se a pasta existe: {folder_path}")
        
        # Tentar listar a pasta
        url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose"
        }
        
        response = await make_request("GET", url, headers=headers)
        
        exists = response.status_code == 200
        logger.info(f"[REPOSITORY] Pasta {folder_path} existe: {exists}")
        return exists
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao verificar pasta: {str(e)}")
        logger.error(traceback.format_exc())
        return False

async def create_folder(token, site_url, folder_path):
    """Cria uma pasta no SharePoint."""
    try:
        logger.info(f"[REPOSITORY] Criando pasta: {folder_path}")
        
        # Extrair o caminho pai e o nome da nova pasta
        parent_path = "/".join(folder_path.split("/")[:-1])
        folder_name = folder_path.split("/")[-1]
        
        url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{parent_path}')/Folders/add('{folder_name}')"
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json;odata=verbose",
            "Content-Type": "application/json;odata=verbose"
        }
        
        response = await make_request("POST", url, headers=headers, json_data={})
        
        if response.status_code in [200, 201]:
            logger.info(f"[REPOSITORY] Pasta criada com sucesso: {folder_path}")
            return True
        else:
            logger.error(f"[REPOSITORY] Erro ao criar pasta: {response.status_code}")
            logger.error(f"[REPOSITORY] Resposta: {response.text}")
            return False
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao criar pasta: {str(e)}")
        logger.error(traceback.format_exc())
        return False

async def prepare_repository_folders(token, site_url):
    """Prepara as pastas do repositório, criando a estrutura de ano.mês conforme necessário."""
    try:
        logger.info("[REPOSITORY] Preparando pastas do repositório")
        
        # Obtém o ano.mês atual
        current_date = datetime.now()
        year_month_folder = f"{current_date.year}.{current_date.month:02d}"
        logger.info(f"[REPOSITORY] Pasta do ano.mês: {year_month_folder}")
        
        results = {}
        
        # Verifica cada pasta do repositório
        for folder_type, base_path in REPOSITORY_PATHS.items():
            logger.info(f"[REPOSITORY] Verificando pasta {folder_type}: {base_path}")
            
            # Verifica se a pasta base existe
            base_exists = await check_folder_exists(token, site_url, base_path)
            
            if not base_exists:
                logger.error(f"[REPOSITORY] Pasta base {folder_type} não existe: {base_path}")
                results[folder_type] = {"success": False, "reason": "Pasta base não existe"}
                continue
                
            # Verifica/cria a pasta do ano.mês
            year_month_path = f"{base_path}/{year_month_folder}"
            year_month_exists = await check_folder_exists(token, site_url, year_month_path)
            
            if not year_month_exists:
                logger.info(f"[REPOSITORY] Criando pasta ano.mês para {folder_type}: {year_month_path}")
                create_result = await create_folder(token, site_url, year_month_path)
                
                if create_result:
                    logger.info(f"[REPOSITORY] Pasta ano.mês criada com sucesso para {folder_type}")
                    results[folder_type] = {"success": True, "path": year_month_path}
                else:
                    logger.error(f"[REPOSITORY] Falha ao criar pasta ano.mês para {folder_type}")
                    results[folder_type] = {"success": False, "reason": "Falha ao criar pasta ano.mês"}
            else:
                logger.info(f"[REPOSITORY] Pasta ano.mês já existe para {folder_type}")
                results[folder_type] = {"success": True, "path": year_month_path}
        
        return results, year_month_folder
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao preparar pastas: {str(e)}")
        logger.error(traceback.format_exc())
        return {}, ""

async def make_request(method, url, headers=None, data=None, json_data=None, files=None):
    """Faz uma requisição HTTP para o SharePoint."""
    import aiohttp
    import json as json_module
    
    try:
        logger.debug(f"[REPOSITORY] Requisição {method} para: {url}")
        
        if headers:
            logger.debug(f"[REPOSITORY] Headers: {headers}")
        
        async with aiohttp.ClientSession() as session:
            if method.upper() == "GET":
                async with session.get(url, headers=headers) as response:
                    content = await response.read()
                    
                    # Criar um objeto de resposta similar ao do requests
                    class Response:
                        def __init__(self, status_code, content, headers):
                            self.status_code = status_code
                            self.content = content
                            self._headers = headers
                            self._text = None
                            
                        @property
                        def text(self):
                            if self._text is None:
                                self._text = self.content.decode('utf-8', errors='replace')
                            return self._text
                            
                        def json(self):
                            return json_module.loads(self.text)
                    
                    return Response(response.status, content, response.headers)
                    
            elif method.upper() == "POST":
                async with session.post(url, headers=headers, data=data, json=json_data) as response:
                    content = await response.read()
                    
                    class Response:
                        def __init__(self, status_code, content, headers):
                            self.status_code = status_code
                            self.content = content
                            self._headers = headers
                            self._text = None
                            
                        @property
                        def text(self):
                            if self._text is None:
                                self._text = self.content.decode('utf-8', errors='replace')
                            return self._text
                            
                        def json(self):
                            return json_module.loads(self.text)
                    
                    return Response(response.status, content, response.headers)
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro na requisição: {str(e)}")
        logger.error(traceback.format_exc())
        
        # Retornar um objeto de resposta com erro
        class ErrorResponse:
            def __init__(self):
                self.status_code = 500
                self.content = b""
                self._text = f"Erro na requisição: {str(e)}"
                
            @property
            def text(self):
                return self._text
                
            def json(self):
                return {"error": self.text}
                
        return ErrorResponse()

async def copy_file_to_repository(token, site_url, source_path, file_name, destination_path):
    """Copia um arquivo de uma pasta para outra no SharePoint."""
    try:
        logger.info(f"[REPOSITORY] Copiando arquivo {file_name} de {source_path} para {destination_path}")
        
        # Download do arquivo
        file_content = await download_file(token, site_url, source_path, file_name)
        
        if not file_content:
            logger.error(f"[REPOSITORY] Não foi possível baixar o arquivo {file_name}")
            return False
        
        # Upload para o destino
        success = await upload_file(token, site_url, file_content, file_name, destination_path)
        
        if success:
            logger.info(f"[REPOSITORY] Arquivo {file_name} copiado com sucesso para {destination_path}")
            return True
        else:
            logger.error(f"[REPOSITORY] Falha ao copiar arquivo {file_name} para {destination_path}")
            return False
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao copiar arquivo: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@router.post("/copy-to-repository")
async def copy_files_to_repository():
    """
    Endpoint para copiar arquivos das pastas de origem para o repositório,
    de acordo com os critérios especificados.
    """
    try:
        logger.info("[REPOSITORY] Iniciando processo de cópia para o repositório")
        
        # Obter token e URL do site
        token, site_url = await get_token_and_site_url()
        
        # Preparar pastas do repositório
        folder_results, year_month_folder = await prepare_repository_folders(token, site_url)
        
        if not year_month_folder:
            logger.error("[REPOSITORY] Falha ao preparar pastas do repositório")
            raise HTTPException(status_code=500, detail="Falha ao preparar pastas do repositório")
        
        # Inicializar contadores
        total_files = 0
        copied_files = 0
        failed_files = 0
        skipped_files = 0
        
        # Processar arquivos NFSERV - Critério 1: QPE-\d{6}[A-Za-z]
        logger.info("[REPOSITORY] Processando arquivos NFSERV com padrão QPE-\\d{6}[A-Za-z]")
        nfserv_files = await list_files(token, site_url, PATHS["NFSERV"])
        
        for file in nfserv_files:
            file_name = file.get("Name")
            total_files += 1
            
            # Verificar se o arquivo corresponde ao critério
            if re.search(r"QPE-\d{6}[A-Za-z]", file_name):
                logger.info(f"[REPOSITORY] Arquivo NFSERV {file_name} corresponde ao critério 1")
                
                # Verificar se a pasta CADASTRAR foi preparada com sucesso
                if folder_results.get("CADASTRAR", {}).get("success", False):
                    destination_path = folder_results["CADASTRAR"]["path"]
                    
                    # Copiar o arquivo
                    success = await copy_file_to_repository(
                        token, site_url, PATHS["NFSERV"], file_name, destination_path
                    )
                    
                    if success:
                        copied_files += 1
                    else:
                        failed_files += 1
                else:
                    logger.error(f"[REPOSITORY] Pasta CADASTRAR não está pronta, arquivo {file_name} não copiado")
                    skipped_files += 1
            else:
                logger.info(f"[REPOSITORY] Arquivo NFSERV {file_name} não corresponde ao critério 1, verificando critério 2")
                
                # Verificar critério 2: cidade no nome e padrão \d{6}[A-Za-z]\d{2}
                cities = ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]
                has_city = any(city in file_name for city in cities)
                has_pattern = re.search(r"\d{6}[A-Za-z]\d{2}", file_name) is not None
                
                if has_city and has_pattern:
                    logger.info(f"[REPOSITORY] Arquivo NFSERV {file_name} corresponde ao critério 2")
                    
                    # Verificar se a pasta ESCRITURAR foi preparada com sucesso
                    if folder_results.get("ESCRITURAR", {}).get("success", False):
                        destination_path = folder_results["ESCRITURAR"]["path"]
                        
                        # Copiar o arquivo
                        success = await copy_file_to_repository(
                            token, site_url, PATHS["NFSERV"], file_name, destination_path
                        )
                        
                        if success:
                            copied_files += 1
                        else:
                            failed_files += 1
                    else:
                        logger.error(f"[REPOSITORY] Pasta ESCRITURAR não está pronta, arquivo {file_name} não copiado")
                        skipped_files += 1
                else:
                    logger.info(f"[REPOSITORY] Arquivo NFSERV {file_name} não corresponde a nenhum critério, ignorando")
                    skipped_files += 1
        
        # Processar arquivos QPE - Copiar todos para NOTA_FISCAL
        logger.info("[REPOSITORY] Processando arquivos QPE - Copiar todos para NOTA_FISCAL")
        qpe_files = await list_files(token, site_url, PATHS["QPE"])
        
        for file in qpe_files:
            file_name = file.get("Name")
            total_files += 1
            
            # Verificar se a pasta NOTA_FISCAL foi preparada com sucesso
            if folder_results.get("NOTA_FISCAL", {}).get("success", False):
                destination_path = folder_results["NOTA_FISCAL"]["path"]
                
                # Copiar o arquivo
                success = await copy_file_to_repository(
                    token, site_url, PATHS["QPE"], file_name, destination_path
                )
                
                if success:
                    copied_files += 1
                else:
                    failed_files += 1
            else:
                logger.error(f"[REPOSITORY] Pasta NOTA_FISCAL não está pronta, arquivo {file_name} não copiado")
                skipped_files += 1
        
        # Processar arquivos SPB - Copiar todos para NOTA_FISCAL
        logger.info("[REPOSITORY] Processando arquivos SPB - Copiar todos para NOTA_FISCAL")
        spb_files = await list_files(token, site_url, PATHS["SPB"])
        
        for file in spb_files:
            file_name = file.get("Name")
            total_files += 1
            
            # Verificar se a pasta NOTA_FISCAL foi preparada com sucesso
            if folder_results.get("NOTA_FISCAL", {}).get("success", False):
                destination_path = folder_results["NOTA_FISCAL"]["path"]
                
                # Copiar o arquivo
                success = await copy_file_to_repository(
                    token, site_url, PATHS["SPB"], file_name, destination_path
                )
                
                if success:
                    copied_files += 1
                else:
                    failed_files += 1
            else:
                logger.error(f"[REPOSITORY] Pasta NOTA_FISCAL não está pronta, arquivo {file_name} não copiado")
                skipped_files += 1
        
        # Preparar relatório
        logger.info("[REPOSITORY] Processo de cópia concluído")
        logger.info(f"[REPOSITORY] Total de arquivos processados: {total_files}")
        logger.info(f"[REPOSITORY] Arquivos copiados com sucesso: {copied_files}")
        logger.info(f"[REPOSITORY] Arquivos com falha: {failed_files}")
        logger.info(f"[REPOSITORY] Arquivos ignorados: {skipped_files}")
        
        return {
            "success": True,
            "message": "Processo de cópia concluído",
            "details": {
                "total_files": total_files,
                "copied_files": copied_files,
                "failed_files": failed_files,
                "skipped_files": skipped_files,
                "year_month_folder": year_month_folder
            }
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro durante o processo de cópia: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro durante o processo de cópia: {str(e)}")

@router.get("/folder-access-test")
async def test_folder_access():
    """
    Endpoint para testar o acesso às pastas de origem e destino.
    Útil para diagnóstico de problemas de permissão.
    """
    try:
        logger.info("[REPOSITORY] Testando acesso às pastas")
        
        # Obter token e URL do site
        token, site_url = await get_token_and_site_url()
        
        results = {}
        
        # Testar acesso às pastas de origem
        for folder_name, folder_path in PATHS.items():
            folder_exists = await check_folder_exists(token, site_url, folder_path)
            results[folder_name] = {
                "path": folder_path,
                "exists": folder_exists
            }
            
            if folder_exists:
                # Tentar listar arquivos
                files = await list_files(token, site_url, folder_path)
                results[folder_name]["files_count"] = len(files)
                if files:
                    results[folder_name]["sample_files"] = [f.get("Name") for f in files[:3]]
        
        # Testar acesso às pastas de destino
        for folder_name, folder_path in REPOSITORY_PATHS.items():
            folder_exists = await check_folder_exists(token, site_url, folder_path)
            results[f"REPO_{folder_name}"] = {
                "path": folder_path,
                "exists": folder_exists
            }
            
            if folder_exists:
                # Tentar listar arquivos
                files = await list_files(token, site_url, folder_path)
                results[f"REPO_{folder_name}"]["files_count"] = len(files)
                if files:
                    results[f"REPO_{folder_name}"]["sample_files"] = [f.get("Name") for f in files[:3]]
        
        return {
            "success": True,
            "message": "Teste de acesso concluído",
            "results": results
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro durante o teste de acesso: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Erro durante o teste de acesso: {str(e)}")