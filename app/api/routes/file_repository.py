import os
import re
import logging
import traceback
import urllib.parse
import aiohttp
from datetime import datetime
from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any, Optional
from io import BytesIO
import requests
from dotenv import load_dotenv
import asyncio

from app.core.auth import SharePointAuth
from app.api.routes.file_processor import (
    make_request, 
    list_files, 
    download_file, 
    check_folder_exists, 
    create_folder,
    delete_file
)

# Configuração de logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# URL base para acesso ao SharePoint Contratos (com base no curl que funcionou)
SHAREPOINT_CONTRATOS_BASE_URL = "https://weg365.sharepoint.com/teams/BR-TI-TIN/contratos"

router = APIRouter(
    prefix="/files-repository",
    tags=["files-repository"],
    responses={404: {"description": "Not found"}},
)

# Função para codificar corretamente os caminhos do SharePoint
def encode_sharepoint_path(path):
    """
    Codifica o caminho preservando underscores como requerido pelo SharePoint.
    IMPORTANTE: Não deve converter underscores para %5F
    """
    if not path:
        return ""
    
    # Remove barras extras no início e fim
    path = path.strip("/")
    
    # Remove barras duplas
    path = re.sub(r"//+", "/", path)
    
    # Adiciona barra no início
    path = "/" + path
    
    # Log do caminho que será usado
    logger.info(f"[ENCODE] Caminho formatado (sem codificação): {path}")
    
    # Para o SharePoint, vamos retornar sem codificação adicional
    # Esta é a parte mais importante - os testes mostraram que precisamos 
    # manter os underscores e caracteres especiais como estão
    return path

# Caminhos das pastas de origem - mantendo os originais para referência
ORIGINAL_PATHS = {
    "ENTRADA": "/teams/BR-TI-TIN/AutomaoFinanas/ENTRADA",   
    "R189": "/teams/BR-TI-TIN/AutomaoFinanas/R189",
    "QPE": "/teams/BR-TI-TIN/AutomaoFinanas/QPE",
    "NFSERV": "/teams/BR-TI-TIN/AutomaoFinanas/NFSERV",
    "SPB": "/teams/BR-TI-TIN/AutomaoFinanas/SPB",
}

# Caminhos das pastas de origem codificados para uso em URLs
PATHS = {key: encode_sharepoint_path(path) for key, path in ORIGINAL_PATHS.items()}

# Caminhos das pastas de destino (repositório) - USANDO CAMINHOS SEM CODIFICAÇÃO
REPOSITORY_PATHS = {
    "CADASTRAR": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar",
    "ESCRITURAR": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Escriturar",
    "NOTA_FISCAL": "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Nota_Fiscal_Serviço"
}

# Variável global para controlar o estado de cancelamento
PROCESS_CANCELLED = False

async def get_sharepoint_auth():
    """
    Obtém o token e a URL do site SharePoint da mesma maneira que o file_processor.py
    """
    from app.core.auth import SharePointAuth
    
    try:
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token de autenticação")
            return None, None
            
        return token, site_url
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao obter autenticação: {str(e)}")
        return None, None

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
            year_month_path = f"{base_path}/{encode_sharepoint_path(year_month_folder)}"
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

async def copy_file_to_repository(token, site_url, source_path, file_name, destination_path):
    """
    Copia um arquivo de uma pasta para outra no SharePoint.
    """
    try:
        # Log para monitoramento - início da operação
        logger.info(f"[REPOSITORY] Iniciando cópia do arquivo {file_name}")
        logger.info(f"[REPOSITORY] Origem: {source_path}")
        logger.info(f"[REPOSITORY] Destino: {destination_path}")
        
        # Verificar se o processo foi cancelado
        if check_if_cancelled():
            logger.info(f"[REPOSITORY] Cópia do arquivo {file_name} cancelada pelo usuário")
            return False
            
        # Codificar corretamente os caminhos
        encoded_source_path = encode_sharepoint_path(source_path)
        
        # Download do arquivo
        start_download = datetime.now()
        file_content = await download_file(token, site_url, encoded_source_path, file_name)
        download_duration = (datetime.now() - start_download).total_seconds()
        
        if not file_content:
            logger.error(f"[REPOSITORY] Não foi possível baixar o arquivo {file_name}")
            return False
        
        # Log de sucesso do download
        if isinstance(file_content, BytesIO):
            file_size = file_content.getbuffer().nbytes
        else:
            file_size = len(file_content)
            
        logger.info(f"[REPOSITORY] Download concluído em {download_duration:.2f}s, tamanho: {file_size} bytes")
        
        # Verificar novamente se o processo foi cancelado após download
        if check_if_cancelled():
            logger.info(f"[REPOSITORY] Cópia do arquivo {file_name} cancelada após download")
            return False
        
        # Upload para o destino
        start_upload = datetime.now()
        success = await upload_file_to_repository(token, file_content, file_name, destination_path)
        upload_duration = (datetime.now() - start_upload).total_seconds()
        
        if success:
            logger.info(f"[REPOSITORY] Arquivo {file_name} copiado com sucesso em {upload_duration:.2f}s")
            return True
        else:
            logger.error(f"[REPOSITORY] Falha ao copiar arquivo {file_name}, tempo: {upload_duration:.2f}s")
            return False
    except Exception as e:
        logger.error(f"[REPOSITORY] Exceção ao copiar arquivo: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@router.post("/copy-to-repository")
async def copy_files_to_repository(clean_folders: bool = True):
    """
    Endpoint para copiar arquivos para o repositório, usando estrutura de pastas por data.
    
    Args:
        clean_folders: Se True, limpa as pastas do mês atual antes de usar
    """
    try:
        global PROCESS_CANCELLED
        # Resetar o estado de cancelamento no início do processo
        PROCESS_CANCELLED = False
        
        logger.info("[REPOSITORY] Iniciando processo de cópia para o repositório")
        logger.info(f"[REPOSITORY] Opção de limpar pastas: {clean_folders}")
        
        # Obter token e URL do site
        from app.core.auth import SharePointAuth
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token")
            raise HTTPException(status_code=500, detail="Falha ao obter token de autenticação")
        
        logger.info(f"[REPOSITORY] Token obtido com sucesso. Site URL: {site_url}")
        
        # Obter data atual para estrutura de pastas
        current_date = datetime.now()
        current_year = str(current_date.year)
        current_year_month = f"{current_date.year}.{current_date.month:02d}"
        logger.info(f"[REPOSITORY] Estrutura de pastas: ano={current_year}, mês={current_year_month}")
        
        # Preparar estrutura de pastas por data para cada repositório
        dest_folders = {}
        dest_paths = {}
        
        for folder_name, base_path in REPOSITORY_PATHS.items():
            # Verificar cancelamento
            if check_if_cancelled():
                logger.info("[REPOSITORY] Processo cancelado durante preparação de pastas")
                return {"success": False, "message": "Processo cancelado pelo usuário", "cancelled": True}
            
            # Montar caminhos para estrutura de pastas
            year_path = f"{base_path}/{current_year}"
            year_month_path = f"{year_path}/{current_year_month}"
            
            # Verificar/criar pasta do ano
            year_folder_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, year_path)
            if not year_folder_exists:
                logger.info(f"[REPOSITORY] Criando pasta do ano: {year_path}")
                year_created = await create_folder(token, SHAREPOINT_CONTRATOS_BASE_URL, year_path)
                if not year_created:
                    logger.error(f"[REPOSITORY] Falha ao criar pasta do ano: {year_path}")
                    dest_folders[folder_name] = False
                    continue
            
            # Verificar/criar pasta do mês
            month_folder_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, year_month_path)
            if month_folder_exists and clean_folders:
                # Limpar pasta do mês se já existir e clean_folders=True
                logger.info(f"[REPOSITORY] Limpando pasta existente: {year_month_path}")
                await clean_folder(token, year_month_path)
            elif not month_folder_exists:
                # Criar pasta do mês se não existir
                logger.info(f"[REPOSITORY] Criando pasta do mês: {year_month_path}")
                month_created = await create_folder(token, SHAREPOINT_CONTRATOS_BASE_URL, year_month_path)
                if not month_created:
                    logger.error(f"[REPOSITORY] Falha ao criar pasta do mês: {year_month_path}")
                    dest_folders[folder_name] = False
                    continue
            
            # Armazenar caminhos e status
            dest_folders[folder_name] = True
            dest_paths[folder_name] = year_month_path
            logger.info(f"[REPOSITORY] Pasta {folder_name} preparada: {year_month_path}")
        
        # Contadores
        total_files = 0
        copied_files = 0
        failed_files = 0
        skipped_files = 0
        
        # Processamento de arquivos NFSERV
        if dest_folders.get("CADASTRAR") or dest_folders.get("ESCRITURAR"):
            logger.info("[REPOSITORY] Processando arquivos NFSERV")
            nfserv_files = await list_files(token, site_url, PATHS["NFSERV"])
            total_files += len(nfserv_files)
            
            for file in nfserv_files:
                # Verificar cancelamento
                if check_if_cancelled():
                    logger.info("[REPOSITORY] Processo cancelado durante processamento de NFSERV")
                    return {
                        "success": False,
                        "message": "Processo cancelado pelo usuário",
                        "cancelled": True,
                        "details": {
                            "total_files": total_files,
                            "copied_files": copied_files,
                            "failed_files": failed_files,
                            "skipped_files": skipped_files
                        }
                    }
                    
                file_name = file.get("Name")
                file_name_upper = file_name.upper()
                
                # Critério 1: QPE-<6 dígitos><letra> -> CADASTRAR (case-insensitive)
                if re.search(r"QPE-\d{6}[A-Z]", file_name_upper) and dest_folders.get("CADASTRAR"):
                    logger.info(f"[REPOSITORY] Arquivo {file_name} corresponde ao critério para CADASTRAR")
                    
                    # Usar o caminho final com estrutura de ano/ano.mês
                    final_dest_path = dest_paths["CADASTRAR"]
                    
                    # Copiar o arquivo
                    success = await copy_file_to_repository(
                        token, site_url, PATHS["NFSERV"], file_name, final_dest_path
                    )
                    
                    if success:
                        copied_files += 1
                    else:
                        failed_files += 1
                    continue
                
                # Critério 2: código de cidade + <6 dígitos><letra><2 dígitos> -> ESCRITURAR
                cities = ["BLU", "POA", "VIX", "SPB", "REC", "BHO"]
                has_city = any(city in file_name_upper for city in cities)
                has_pattern = re.search(r"\d{6}[A-Z]\d{2}", file_name_upper) is not None
                
                if has_city and has_pattern and dest_folders.get("ESCRITURAR"):
                    logger.info(f"[REPOSITORY] Arquivo {file_name} corresponde ao critério para ESCRITURAR")
                    
                    # Usar o caminho final com estrutura de ano/ano.mês
                    final_dest_path = dest_paths["ESCRITURAR"]
                    
                    # Copiar o arquivo
                    success = await copy_file_to_repository(
                        token, site_url, PATHS["NFSERV"], file_name, final_dest_path
                    )
                    
                    if success:
                        copied_files += 1
                    else:
                        failed_files += 1
                else:
                    logger.info(f"[REPOSITORY] Arquivo {file_name} não corresponde a nenhum critério ou pasta de destino não existe, ignorando")
                    skipped_files += 1
        else:
            logger.error("[REPOSITORY] Pastas CADASTRAR e ESCRITURAR não existem, ignorando arquivos NFSERV")
            nfserv_files = await list_files(token, site_url, PATHS["NFSERV"])
            total_files += len(nfserv_files)
            skipped_files += len(nfserv_files)
        
        # Verificar cancelamento antes de processar QPE
        if check_if_cancelled():
            logger.info("[REPOSITORY] Processo cancelado antes de processar QPE")
            return {
                "success": False,
                "message": "Processo cancelado pelo usuário",
                "cancelled": True,
                "details": {
                    "total_files": total_files,
                    "copied_files": copied_files,
                    "failed_files": failed_files,
                    "skipped_files": skipped_files
                }
            }
        
        # Processamento de arquivos QPE -> NOTA_FISCAL
        if dest_folders.get("NOTA_FISCAL"):
            logger.info("[REPOSITORY] Processando arquivos QPE")
            qpe_files = await list_files(token, site_url, PATHS["QPE"])
            total_files += len(qpe_files)
            
            # Usar o caminho final com estrutura de ano/ano.mês
            final_dest_path = dest_paths["NOTA_FISCAL"]
            
            for file in qpe_files:
                # Verificar cancelamento
                if check_if_cancelled():
                    logger.info("[REPOSITORY] Processo cancelado durante processamento de QPE")
                    return {
                        "success": False,
                        "message": "Processo cancelado pelo usuário",
                        "cancelled": True,
                        "details": {
                            "total_files": total_files,
                            "copied_files": copied_files,
                            "failed_files": failed_files,
                            "skipped_files": skipped_files
                        }
                    }
                    
                file_name = file.get("Name")
                logger.info(f"[REPOSITORY] Processando arquivo QPE: {file_name}")
                
                # Copiar o arquivo para a pasta NOTA_FISCAL
                success = await copy_file_to_repository(
                    token, site_url, PATHS["QPE"], file_name, final_dest_path
                )
                
                if success:
                    copied_files += 1
                    logger.info(f"[REPOSITORY] Arquivo QPE {file_name} copiado com sucesso")
                else:
                    failed_files += 1
                    logger.error(f"[REPOSITORY] Falha ao copiar arquivo QPE {file_name}")
        else:
            logger.error("[REPOSITORY] Pasta NOTA_FISCAL não existe, ignorando arquivos QPE")
            qpe_files = await list_files(token, site_url, PATHS["QPE"])
            total_files += len(qpe_files)
            skipped_files += len(qpe_files)
        
        # Verificar cancelamento antes de processar SPB
        if check_if_cancelled():
            logger.info("[REPOSITORY] Processo cancelado antes de processar SPB")
            return {
                "success": False,
                "message": "Processo cancelado pelo usuário",
                "cancelled": True,
                "details": {
                    "total_files": total_files,
                    "copied_files": copied_files,
                    "failed_files": failed_files,
                    "skipped_files": skipped_files
                }
            }
        
        # Processamento de arquivos SPB -> NOTA_FISCAL
        if dest_folders.get("NOTA_FISCAL"):
            logger.info("[REPOSITORY] Processando arquivos SPB")
            spb_files = await list_files(token, site_url, PATHS["SPB"])
            total_files += len(spb_files)
            
            # Usar o caminho final com estrutura de ano/ano.mês
            final_dest_path = dest_paths["NOTA_FISCAL"]
            
            for file in spb_files:
                # Verificar cancelamento
                if check_if_cancelled():
                    logger.info("[REPOSITORY] Processo cancelado durante processamento de SPB")
                    return {
                        "success": False,
                        "message": "Processo cancelado pelo usuário",
                        "cancelled": True,
                        "details": {
                            "total_files": total_files,
                            "copied_files": copied_files,
                            "failed_files": failed_files,
                            "skipped_files": skipped_files
                        }
                    }
                    
                file_name = file.get("Name")
                logger.info(f"[REPOSITORY] Processando arquivo SPB: {file_name}")
                
                # Copiar o arquivo para a pasta NOTA_FISCAL
                success = await copy_file_to_repository(
                    token, site_url, PATHS["SPB"], file_name, final_dest_path
                )
                
                if success:
                    copied_files += 1
                    logger.info(f"[REPOSITORY] Arquivo SPB {file_name} copiado com sucesso")
                else:
                    failed_files += 1
                    logger.error(f"[REPOSITORY] Falha ao copiar arquivo SPB {file_name}")
        else:
            logger.error("[REPOSITORY] Pasta NOTA_FISCAL não existe, ignorando arquivos SPB")
            spb_files = await list_files(token, site_url, PATHS["SPB"])
            total_files += len(spb_files)
            skipped_files += len(spb_files)
        
        # Relatório
        logger.info("[REPOSITORY] Processo de cópia concluído")
        logger.info(f"[REPOSITORY] Total de arquivos: {total_files}")
        logger.info(f"[REPOSITORY] Copiados com sucesso: {copied_files}")
        logger.info(f"[REPOSITORY] Falhas: {failed_files}")
        logger.info(f"[REPOSITORY] Ignorados: {skipped_files}")
        
        return {
            "success": True,
            "message": "Processo de cópia concluído",
            "details": {
                "total_files": total_files,
                "copied_files": copied_files,
                "failed_files": failed_files,
                "skipped_files": skipped_files,
                "cleaned_folders": clean_folders
            },
            "destination_folders": {
                k: {"exists": v, "path": dest_paths.get(k)} 
                for k, v in dest_folders.items()
            }
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro durante o processo: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/folder-access-test")
async def test_folder_access():
    """
    Endpoint para testar o acesso às pastas de origem e destino.
    Útil para diagnóstico de problemas de permissão.
    """
    try:
        logger.info("[REPOSITORY] Testando acesso às pastas")
        
        # Obter token e URL do site
        token, site_url = await get_sharepoint_auth()
        
        if not token:
            logger.error("[REPOSITORY] Falha ao obter token de autenticação")
            raise HTTPException(status_code=500, detail="Falha ao obter token de autenticação")
        
        results = {}
        
        # Testar acesso às pastas de origem
        for folder_name, folder_path in PATHS.items():
            folder_exists = await check_folder_exists(token, site_url, folder_path)
            results[folder_name] = {
                "path": folder_path,
                "original_path": ORIGINAL_PATHS[folder_name],
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
                "original_path": REPOSITORY_PATHS[folder_name],
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

@router.get("/test-simple-upload")
async def test_simple_upload():
    """
    Endpoint para testar o upload com codificação correta de URL.
    O frontend pode chamar esta API para verificar se a solução funciona.
    """
    try:
        # Obter autenticação
        from app.core.auth import SharePointAuth
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            return {"success": False, "error": "Falha ao obter token"}
        
        # Caminhos para teste (os três principais repositórios)
        test_paths = [
            ORIGINAL_PATHS["CADASTRAR"],
            ORIGINAL_PATHS["ESCRITURAR"],
            ORIGINAL_PATHS["NOTA_FISCAL"]
        ]
        
        results = []
        
        for test_path in test_paths:
            try:
                # Codificação correta: preservar underscores
                path_parts = test_path.split('/')
                encoded_parts = []
                
                for part in path_parts:
                    if part:
                        # Preservar os underscores
                        temp_part = part.replace('_', '___TEMP___')
                        # Codificar a parte
                        encoded_part = urllib.parse.quote(temp_part)
                        # Restaurar os underscores
                        encoded_part = encoded_part.replace('___TEMP___', '_')
                        encoded_parts.append(encoded_part)
                
                encoded_path = '/' + '/'.join(encoded_parts)
                
                logger.info(f"Testando caminho: {test_path}")
                logger.info(f"Codificado como: {encoded_path}")
                
                # Criar um arquivo de teste simples
                test_content = f"Teste de upload para {test_path} - {datetime.now()}".encode('utf-8')
                test_filename = f"teste_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
                
                # Tentar fazer upload
                upload_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded_path}')/Files/add(url='{test_filename}',overwrite=true)"
                
                headers = {
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/octet-stream",
                    "Accept": "application/json;odata=verbose"
                }
                
                logger.info(f"URL de upload: {upload_url}")
                
                response = await make_request(upload_url, method="POST", data=test_content, headers=headers)
                
                logger.info(f"Resposta de upload: {response.status_code}")
                success = response.status_code == 200 or response.status_code == 201
                
                results.append({
                    "path": test_path,
                    "encoded_path": encoded_path,
                    "success": success,
                    "status_code": response.status_code,
                    "filename": test_filename
                })
            
            except Exception as e:
                results.append({
                    "path": test_path,
                    "error": str(e),
                    "success": False
                })
        
        return {
            "results": results,
            "overall_success": any(r["success"] for r in results)
        }
    except Exception as e:
        logger.error(f"Erro no teste global: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

@router.get("/test-curl-exact")
async def test_curl_exact():
    """
    Implementação exata do comando curl que funcionou, com logs detalhados
    """
    try:
        # Obter autenticação
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            return {"success": False, "error": "Falha ao obter token"}
        
        # Logs para verificar o token e site_url
        logger.info(f"[CURL-EXACT] Token obtido (primeiros 20 caracteres): {token[:20]}...")
        logger.info(f"[CURL-EXACT] Site URL: {site_url}")
        logger.info(f"[CURL-EXACT] URL base do Contratos: {SHAREPOINT_CONTRATOS_BASE_URL}")
        
        # Usar exatamente o mesmo caminho do curl
        folder_path = "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar"
        test_filename = f"teste_curl_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
        
        # Criar um arquivo de teste simples
        test_content = f"Teste exato de curl - {datetime.now()}".encode('utf-8')
        
        # Construir a URL usando nossa constante global
        url = f"{SHAREPOINT_CONTRATOS_BASE_URL}/_api/web/GetFolderByServerRelativeUrl('{folder_path}')/Files/add(overwrite=true,url='{test_filename}')"
        
        logger.info(f"[CURL-EXACT] URL construída: {url}")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Accept": "application/json;odata=verbose"
        }
        
        logger.info(f"[CURL-EXACT] Headers: {headers}")
        
        # Fazer o upload com tratamento de erros melhorado
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(url, headers=headers, data=test_content, timeout=60)
            )
            
            logger.info(f"[CURL-EXACT] Status code: {response.status_code}")
            logger.info(f"[CURL-EXACT] Resposta: {response.text[:500]}...")
            
            success = response.status_code in [200, 201]
            
            return {
                "success": success,
                "status_code": response.status_code,
                "path": folder_path,
                "filename": test_filename,
                "timestamp": str(datetime.now()),
                "response_snippet": response.text[:200] if response.text else None
            }
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[CURL-EXACT] Erro de conexão: {str(e)}")
            return {"success": False, "error": f"Erro de conexão: {str(e)}"}
        except requests.exceptions.Timeout as e:
            logger.error(f"[CURL-EXACT] Timeout na requisição: {str(e)}")
            return {"success": False, "error": f"Timeout na requisição: {str(e)}"}
        except Exception as e:
            logger.error(f"[CURL-EXACT] Erro: {str(e)}")
            return {"success": False, "error": f"Erro genérico: {str(e)}"}
            
    except Exception as e:
        logger.error(f"[CURL-EXACT] Erro: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

async def upload_file_to_repository(token, file_content, file_name, destination_path):
    """
    Função de upload que usa diretamente a URL que sabemos que funciona.
    Esta função substitui a chamada para 'upload_file' em copy_file_to_repository.
    """
    try:
        # IMPORTANTE: Usar a URL base correta da constante global
        encoded_file_name = urllib.parse.quote(file_name)
        
        # Construir URL usando a constante global
        upload_url = f"{SHAREPOINT_CONTRATOS_BASE_URL}/_api/web/GetFolderByServerRelativeUrl('{destination_path}')/Files/add(overwrite=true,url='{encoded_file_name}')"
        
        logger.info(f"[UPLOAD_REPO] URL completa: {upload_url}")
        
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/octet-stream",
            "Accept": "application/json;odata=verbose"
        }
        
        # Se file_content é BytesIO, precisamos obter os bytes reais
        if isinstance(file_content, BytesIO):
            file_content.seek(0)
            content = file_content.read()
        else:
            content = file_content
        
        # Fazer o request com requests (síncrono mas dentro de async function)
        try:
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None, 
                lambda: requests.post(upload_url, headers=headers, data=content, timeout=60)
            )
            
            logger.info(f"[UPLOAD_REPO] Status: {response.status_code}")
            
            if response.status_code in [200, 201]:
                logger.info(f"[UPLOAD_REPO] Arquivo {file_name} enviado com sucesso para {destination_path}")
                return True
            else:
                logger.error(f"[UPLOAD_REPO] Falha ao enviar arquivo {file_name}: {response.status_code}")
                logger.error(f"[UPLOAD_REPO] Resposta: {response.text}")
                return False
                
        except requests.exceptions.ConnectionError as e:
            logger.error(f"[UPLOAD_REPO] Erro de conexão ao enviar {file_name}: {str(e)}")
            return False
        except requests.exceptions.Timeout as e:
            logger.error(f"[UPLOAD_REPO] Timeout ao enviar {file_name}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"[UPLOAD_REPO] Erro ao enviar {file_name}: {str(e)}")
            return False
            
    except Exception as e:
        logger.error(f"[UPLOAD_REPO] Exceção ao fazer upload: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@router.post("/cancel-process")
async def cancel_process():
    """
    Cancela o processo de cópia de arquivos em andamento.
    """
    global PROCESS_CANCELLED
    try:
        logger.info("[REPOSITORY] Solicitação de cancelamento de processo recebida")
        PROCESS_CANCELLED = True
        return {"success": True, "message": "Processo de cópia cancelado"}
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao cancelar processo: {str(e)}")
        return {"success": False, "error": str(e)}

def check_if_cancelled():
    """
    Verifica se o processo atual foi cancelado.
    
    Returns:
        bool: True se o processo foi cancelado, False caso contrário
    """
    global PROCESS_CANCELLED
    return PROCESS_CANCELLED

@router.post("/reset-process")
async def reset_process():
    """
    Reinicia o estado do processo, permitindo que um novo comece.
    """
    global PROCESS_CANCELLED
    try:
        logger.info("[REPOSITORY] Reiniciando estado do processo")
        PROCESS_CANCELLED = False
        return {"success": True, "message": "Estado do processo reiniciado"}
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao reiniciar processo: {str(e)}")
        return {"success": False, "error": str(e)}

@router.get("/process-status")
async def get_process_status():
    """
    Retorna o status atual do processo.
    """
    global PROCESS_CANCELLED
    try:
        status = "cancelled" if PROCESS_CANCELLED else "active"
        return {
            "success": True,
            "status": status
        }
    except Exception as e:
        logger.error(f"[REPOSITORY] Erro ao obter status do processo: {str(e)}")
        return {"success": False, "error": str(e)}

@router.get("/test-url-formation")
async def test_url_formation():
    """
    Endpoint para testar a formação de URLs para o SharePoint.
    Útil para diagnóstico de problemas com caminhos.
    """
    try:
        # Obter autenticação
        token, site_url = await get_sharepoint_auth()
        
        if not token:
            return {"success": False, "error": "Falha ao obter token de autenticação"}
        
        # Teste URLs de origem
        src_results = {}
        for key, original_path in ORIGINAL_PATHS.items():
            encoded_path = PATHS[key]
            api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded_path}')"
            
            src_results[key] = {
                "original_path": original_path,
                "encoded_path": encoded_path,
                "api_url": api_url
            }
        
        # Teste URLs de destino
        dest_results = {}
        for key, original_path in REPOSITORY_PATHS.items():
            encoded_path = REPOSITORY_PATHS[key]
            api_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{encoded_path}')"
            
            dest_results[key] = {
                "original_path": original_path,
                "encoded_path": encoded_path,
                "api_url": api_url
            }
        
        # Teste de codificação para um exemplo com caracteres especiais
        special_path = "/Documentos/Repositório_Faturas_Auto/Nota_Fiscal_Serviço"
        encoded_special = encode_sharepoint_path(special_path)
        
        return {
            "success": True,
            "site_url": site_url,
            "source_paths": src_results,
            "destination_paths": dest_results,
            "test_special_chars": {
                "original": special_path,
                "encoded": encoded_special
            }
        }
    except Exception as e:
        logger.error(f"[URL TEST] Erro: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

async def prepare_date_folder_structure(token, site_url, base_folder_path, clean_month_folder=True):
    """
    Prepara a estrutura de pastas por data (ano/ano.mês)
    e retorna o caminho completo para o destino final.
    
    Args:
        token: Token de autenticação
        site_url: URL base do site SharePoint
        base_folder_path: Caminho base (ex: /teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar)
        clean_month_folder: Se True, limpa a pasta do mês se ela já existir
        
    Returns:
        caminho completo para pasta destino (ex: /teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar/2025/2025.04)
    """
    try:
        logger.info(f"[DATE_FOLDER] Preparando estrutura de pastas para {base_folder_path}")
        
        # Obter ano e mês atuais
        current_date = datetime.now()
        current_year = str(current_date.year)
        current_year_month = f"{current_date.year}.{current_date.month:02d}"
        
        logger.info(f"[DATE_FOLDER] Data atual: Ano={current_year}, Mês={current_year_month}")
        
        # Verificar se a pasta do ano existe
        year_folder_path = f"{base_folder_path}/{current_year}"
        year_folder_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, year_folder_path)
        
        # Criar pasta do ano se não existir
        if not year_folder_exists:
            logger.info(f"[DATE_FOLDER] Criando pasta do ano: {year_folder_path}")
            year_folder_created = await create_folder(token, SHAREPOINT_CONTRATOS_BASE_URL, year_folder_path)
            
            if not year_folder_created:
                logger.error(f"[DATE_FOLDER] Falha ao criar pasta do ano: {year_folder_path}")
                return None
            
            logger.info(f"[DATE_FOLDER] Pasta do ano criada com sucesso: {year_folder_path}")
        else:
            logger.info(f"[DATE_FOLDER] Pasta do ano já existe: {year_folder_path}")
        
        # Caminho para pasta ano.mês
        year_month_folder_path = f"{year_folder_path}/{current_year_month}"
        year_month_folder_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, year_month_folder_path)
        
        # Se a pasta ano.mês existir e precisamos limpar
        if year_month_folder_exists and clean_month_folder:
            logger.info(f"[DATE_FOLDER] Limpando conteúdo da pasta ano.mês existente: {year_month_folder_path}")
            cleaned = await clean_folder(token, year_month_folder_path)
            
            if not cleaned:
                logger.warning(f"[DATE_FOLDER] Aviso: Houve problemas ao limpar a pasta {year_month_folder_path}")
                # Continuamos mesmo se houver problemas na limpeza
        elif year_month_folder_exists:
            logger.info(f"[DATE_FOLDER] Pasta ano.mês já existe e não será limpa: {year_month_folder_path}")
        else:
            # Criar pasta ano.mês
            logger.info(f"[DATE_FOLDER] Criando pasta ano.mês: {year_month_folder_path}")
            year_month_folder_created = await create_folder(token, SHAREPOINT_CONTRATOS_BASE_URL, year_month_folder_path)
            
            if not year_month_folder_created:
                logger.error(f"[DATE_FOLDER] Falha ao criar pasta ano.mês: {year_month_folder_path}")
                return None
            
            logger.info(f"[DATE_FOLDER] Pasta ano.mês criada com sucesso: {year_month_folder_path}")
        
        # Retornar o caminho completo para a pasta de destino
        return year_month_folder_path
        
    except Exception as e:
        logger.error(f"[DATE_FOLDER] Erro ao preparar estrutura de pastas: {str(e)}")
        logger.error(traceback.format_exc())
        return None

@router.get("/test-folder-structure")
async def test_folder_structure(clean_folders: bool = True):
    """
    Endpoint para testar a criação da estrutura de pastas por data.
    
    Args:
        clean_folders: Se True, limpa as pastas do mês atual antes de usar
    """
    try:
        # Obter autenticação
        auth = SharePointAuth()
        token = auth.acquire_token()
        site_url = auth.site_url
        
        if not token:
            return {"success": False, "error": "Falha ao obter token"}
        
        # Obter data atual
        current_date = datetime.now()
        current_year = str(current_date.year)
        current_year_month = f"{current_date.year}.{current_date.month:02d}"
        
        # Testar para cada tipo de pasta
        results = {}
        
        for folder_type, base_path in REPOSITORY_PATHS.items():
            try:
                # Construir caminhos
                year_path = f"{base_path}/{current_year}"
                year_month_path = f"{year_path}/{current_year_month}"
                
                # Verificar/criar pasta do ano
                year_folder_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, year_path)
                if not year_folder_exists:
                    logger.info(f"[TEST] Criando pasta do ano: {year_path}")
                    year_created = await create_folder(token, SHAREPOINT_CONTRATOS_BASE_URL, year_path)
                    if not year_created:
                        logger.error(f"[TEST] Falha ao criar pasta do ano: {year_path}")
                        results[folder_type] = {
                            "base_path": base_path,
                            "structure_created": False,
                            "error": "Falha ao criar pasta do ano"
                        }
                        continue
                
                # Verificar/criar pasta do mês
                month_folder_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, year_month_path)
                if month_folder_exists and clean_folders:
                    # Limpar pasta do mês
                    logger.info(f"[TEST] Limpando pasta existente: {year_month_path}")
                    await clean_folder(token, year_month_path)
                elif not month_folder_exists:
                    # Criar pasta do mês
                    logger.info(f"[TEST] Criando pasta do mês: {year_month_path}")
                    month_created = await create_folder(token, SHAREPOINT_CONTRATOS_BASE_URL, year_month_path)
                    if not month_created:
                        logger.error(f"[TEST] Falha ao criar pasta do mês: {year_month_path}")
                        results[folder_type] = {
                            "base_path": base_path,
                            "structure_created": False,
                            "error": "Falha ao criar pasta do mês"
                        }
                        continue
                
                # Testar upload para a pasta
                test_content = f"Teste da estrutura de pastas para {folder_type} - {datetime.now()}".encode('utf-8')
                test_filename = f"teste_estrutura_{folder_type.lower()}_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
                
                # Upload do arquivo
                upload_success = await upload_file_to_repository(token, test_content, test_filename, year_month_path)
                
                results[folder_type] = {
                    "base_path": base_path,
                    "year_path": year_path,
                    "year_month_path": year_month_path,
                    "structure_created": True,
                    "cleaned": clean_folders and month_folder_exists,
                    "test_file_uploaded": upload_success,
                    "test_filename": test_filename if upload_success else None
                }
            except Exception as e:
                logger.error(f"[TEST] Erro ao processar pasta {folder_type}: {str(e)}")
                results[folder_type] = {
                    "base_path": base_path,
                    "structure_created": False,
                    "error": f"Exceção: {str(e)}"
                }
        
        return {
            "success": all(r.get("structure_created", False) for r in results.values()),
            "timestamp": str(datetime.now()),
            "year": current_year,
            "year_month": current_year_month,
            "cleaned_folders": clean_folders,
            "results": results
        }
    except Exception as e:
        logger.error(f"[TEST-STRUCTURE] Erro global: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}

async def clean_folder(token, folder_path):
    """
    Remove todos os arquivos de uma pasta no SharePoint.
    
    Args:
        token: Token de autenticação
        folder_path: Caminho da pasta a ser limpa
        
    Returns:
        bool: True se a limpeza foi bem-sucedida, False caso contrário
    """
    import traceback
    from app.api.routes.file_processor import list_files, delete_file
    logger.info(f"[CLEAN_FOLDER] Iniciando limpeza da pasta: {folder_path}")
    try:
        files = await list_files(token, folder_path)
        logger.info(f"[CLEAN_FOLDER] Arquivos encontrados na pasta '{folder_path}': {files}")
        success_count = 0
        fail_count = 0
        
        for file_name in files:
            logger.info(f"[CLEAN_FOLDER] Tentando remover arquivo: {file_name} da pasta: {folder_path}")
            try:
                result = await delete_file(token, folder_path, file_name)
                logger.info(f"[CLEAN_FOLDER] Resultado da exclusão do arquivo '{file_name}': {result}")
                if result:
                    logger.info(f"[CLEAN_FOLDER] Arquivo removido com sucesso: {file_name}")
                    success_count += 1
                else:
                    logger.error(f"[CLEAN_FOLDER] Falha ao remover arquivo {file_name}")
                    fail_count += 1
            except Exception as e:
                logger.error(f"[CLEAN_FOLDER] Erro ao remover arquivo {file_name}: {str(e)}")
                logger.error(traceback.format_exc())
                fail_count += 1
        logger.info(f"[CLEAN_FOLDER] Resultado final: {success_count} arquivos removidos, {fail_count} falhas na pasta {folder_path}")
        return fail_count == 0
    except Exception as e:
        logger.error(f"[CLEAN_FOLDER] Erro ao limpar pasta: {str(e)}")
        logger.error(traceback.format_exc())
        return False

@router.get("/health-check")
async def sharepoint_health_check():
    """
    Endpoint para verificar a saúde da conexão com o SharePoint.
    Pode ser chamado periodicamente para monitoramento.
    """
    try:
        start_time = datetime.now()
        
        # Obter autenticação
        auth = SharePointAuth()
        token = auth.acquire_token()
        
        if not token:
            return {
                "status": "error", 
                "message": "Falha ao obter token de autenticação",
                "timestamp": str(datetime.now())
            }
        
        # Testar acesso às pastas principais
        results = {}
        
        # Testar pasta de origem de NFSERV
        nfserv_path = PATHS["NFSERV"]
        try:
            nfserv_exists = await check_folder_exists(token, auth.site_url, nfserv_path)
            results["nfserv"] = {
                "path": nfserv_path,
                "exists": nfserv_exists
            }
        except Exception as e:
            results["nfserv"] = {"error": str(e)}
        
        # Testar pasta de destino CADASTRAR
        cadastrar_path = REPOSITORY_PATHS["CADASTRAR"]
        try:
            # Testar acesso e tentar listar arquivos
            cadastrar_exists = await check_folder_exists(token, SHAREPOINT_CONTRATOS_BASE_URL, cadastrar_path)
            results["cadastrar"] = {
                "path": cadastrar_path,
                "exists": cadastrar_exists
            }
            
            if cadastrar_exists:
                # Testar criação de arquivo simples
                test_filename = f"healthcheck_{datetime.now().strftime('%Y%m%d%H%M%S')}.txt"
                test_content = f"Health check: {datetime.now()}".encode('utf-8')
                
                upload_success = await upload_file_to_repository(
                    token, test_content, test_filename, cadastrar_path
                )
                
                results["upload_test"] = {
                    "success": upload_success,
                    "filename": test_filename
                }
        except Exception as e:
            results["cadastrar"] = {"error": str(e)}
        
        # Calcular tempo total
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        return {
            "status": "success" if all(r.get("exists", False) for r in results.values() if "error" not in r) else "warning",
            "timestamp": str(end_time),
            "duration_seconds": duration,
            "results": results
        }
    except Exception as e:
        logger.error(f"[HEALTH] Erro no health check: {str(e)}")
        logger.error(traceback.format_exc())
        return {
            "status": "error",
            "message": str(e),
            "timestamp": str(datetime.now())
        }

@router.get("/debug-auth")
async def debug_auth():
    """
    Endpoint para depurar a autenticação e URLs
    """
    try:
        # Carregar ambiente
        load_dotenv()
        
        # Obter variáveis de ambiente
        client_id = os.getenv("CLIENT_ID")
        client_secret = os.getenv("CLIENT_SECRET")[:5] + "..." if os.getenv("CLIENT_SECRET") else None
        tenant_id = os.getenv("TENANT_ID")
        resource = os.getenv("RESOURCE")
        site_url = os.getenv("SITE_URL")
        
        # Obter token via SharePointAuth
        auth = SharePointAuth()
        token = auth.acquire_token()
        auth_site_url = auth.site_url
        
        # Montar URL como no curl que funcionou
        test_folder = "/teams/BR-TI-TIN/contratos/Telecom/Repositório_Faturas_Auto_Orange/Cadastrar"
        test_filename = "test.txt"
        
        # URL que funcionou no Postman 
        working_url = f"https://weg365.sharepoint.com/teams/BR-TI-TIN/contratos/_api/web/GetFolderByServerRelativeUrl('{test_folder}')/Files/add(overwrite=true,url='{test_filename}')"
        
        # URL que seria construída com SITE_URL
        current_url = f"{site_url}/_api/web/GetFolderByServerRelativeUrl('{test_folder}')/Files/add(overwrite=true,url='{test_filename}')"
        
        # URL que seria construída com auth.site_url
        auth_url = f"{auth_site_url}/_api/web/GetFolderByServerRelativeUrl('{test_folder}')/Files/add(overwrite=true,url='{test_filename}')"
        
        return {
            "env_vars": {
                "client_id": client_id,
                "client_secret_masked": client_secret,
                "tenant_id": tenant_id,
                "resource": resource,
                "site_url": site_url,
            },
            "auth_info": {
                "token_obtained": token is not None,
                "token_first_20": token[:20] + "..." if token else None,
                "auth_site_url": auth_site_url,
            },
            "urls": {
                "working_url_from_curl": working_url,
                "current_url_from_env": current_url,
                "auth_url": auth_url,
            }
        }
    except Exception as e:
        logger.error(f"[DEBUG-AUTH] Erro: {str(e)}")
        logger.error(traceback.format_exc())
        return {"success": False, "error": str(e)}